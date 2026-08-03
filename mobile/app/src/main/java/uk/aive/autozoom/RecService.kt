package uk.aive.autozoom

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.webkit.CookieManager
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import java.io.DataOutputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * 1x1 홈 위젯이 두드리는 녹음기.
 *
 * 왜 WebView 가 아니라 네이티브인가: 위젯을 누른 뒤 화면을 끄고 회의를 하는 게 정상 사용이다.
 * 웹의 MediaRecorder 는 앱이 뒤로 가면 잘린다 — 마이크 타입 포그라운드 서비스만 살아남는다.
 *
 * 녹음이 끝나면 파일을 서버 `/api/record` 로 올린다. 그 뒤 전사·요약·질의응답은 서버가 한다.
 * 인증은 WebView 가 들고 있는 세션 쿠키(az_session)를 그대로 빌려 쓴다 —
 * 앱에 계정 정보를 따로 저장하지 않는다는 원칙은 여기서도 유지한다.
 */
class RecService : Service() {

    private var recorder: MediaRecorder? = null
    private var current: File? = null

    companion object {
        const val ACTION_TOGGLE = "uk.aive.autozoom.TOGGLE"
        private const val BASE = "https://autozoom.ai-ve.uk"
        private const val CHANNEL = "rec"
        private const val NOTI_ONGOING = 1
        private const val NOTI_RESULT = 2

        /** 위젯이 읽는 현재 상태. 프로세스가 죽으면 IDLE 로 돌아간다(=녹음도 없다). */
        @Volatile
        var state: String = RecWidget.IDLE
            private set
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "녹음", NotificationManager.IMPORTANCE_LOW))
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // startForegroundService 로 불려왔으므로 무조건 먼저 포그라운드가 돼야 한다.
        try {
            ServiceCompat.startForeground(
                this, NOTI_ONGOING, ongoingNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } catch (e: Exception) {
            toast("녹음을 시작할 수 없습니다: ${e.javaClass.simpleName}")
            stopSelf()
            return START_NOT_STICKY
        }
        if (recorder == null) start() else stopAndUpload()
        return START_NOT_STICKY
    }

    // ------------------------------------------------------------------ 녹음
    private fun recDir(): File = File(filesDir, "rec").apply { mkdirs() }

    private fun start() {
        val file = File(recDir(), "rec_${System.currentTimeMillis()}.m4a")
        try {
            @Suppress("DEPRECATION")
            val r = if (Build.VERSION.SDK_INT >= 31) MediaRecorder(this) else MediaRecorder()
            r.setAudioSource(MediaRecorder.AudioSource.MIC)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setAudioChannels(1)
            r.setAudioSamplingRate(16000)      // 서버 ASR 이 어차피 16k 모노로 내린다
            r.setAudioEncodingBitRate(32000)   // 두 시간 회의 ≈ 28MB
            r.setOutputFile(file.absolutePath)
            r.prepare()
            r.start()
            recorder = r
            current = file
        } catch (e: Exception) {
            file.delete()
            toast("녹음 시작 실패: ${e.message}")
            finish()
            return
        }
        render(RecWidget.REC)
        notify(NOTI_ONGOING, ongoingNotification())
        // 지난번에 못 올린 녹음이 있으면 이 참에 같이 보낸다(업로드 실패·앱 강제종료 대비).
        Thread { recDir().listFiles()?.forEach { if (it != current) send(it) } }.start()
    }

    private fun stopAndUpload() {
        val file = current
        var usable = file != null
        try {
            recorder?.stop()
        } catch (_: Exception) {          // 1초도 안 되는 녹음은 stop 에서 터지고 파일도 깨진다
            usable = false
            file?.delete()
            toast("녹음이 너무 짧습니다")
        }
        recorder?.release()
        recorder = null
        current = null
        if (!usable || file == null) {    // 올릴 게 없다 — 실패 알림까지 띄우진 않는다
            finish()
            return
        }
        render(RecWidget.UP)
        Thread {
            notify(NOTI_RESULT, resultNotification(send(file)))
            finish()
        }.start()
    }

    /** 업로드 성공하면 파일을 지운다. 실패하면 남겨 뒀다가 다음 녹음 때 다시 보낸다. */
    private fun send(file: File): Boolean {
        val cookie = CookieManager.getInstance().getCookie(BASE)
        if (cookie.isNullOrBlank()) return false          // 아직 로그인 전 — 파일은 보존
        val boundary = "az-${System.nanoTime()}"
        var conn: HttpURLConnection? = null
        return try {
            conn = (URL("$BASE/api/record").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = 20_000
                readTimeout = 600_000
                setRequestProperty("Cookie", cookie)
                setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
                setChunkedStreamingMode(1 shl 16)
            }
            DataOutputStream(conn.outputStream.buffered()).use { out ->
                out.writeBytes("--$boundary\r\nContent-Disposition: form-data; " +
                    "name=\"audio\"; filename=\"${file.name}\"\r\n" +
                    "Content-Type: audio/mp4\r\n\r\n")
                file.inputStream().use { it.copyTo(out) }
                out.writeBytes("\r\n--$boundary--\r\n")
            }
            (conn.responseCode == 200).also { if (it) file.delete() }
        } catch (_: Exception) {
            false
        } finally {
            conn?.disconnect()
        }
    }

    private fun finish() {
        render(RecWidget.IDLE)
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        // 시스템이 서비스를 걷어가도 녹음 파일은 남는다 → 다음 녹음 때 올라간다.
        try { recorder?.stop() } catch (_: Exception) { }
        recorder?.release()
        recorder = null
        if (state != RecWidget.UP) render(RecWidget.IDLE)
        super.onDestroy()
    }

    // ------------------------------------------------------------------ 알림·위젯
    private fun render(s: String) {
        state = s
        RecWidget.renderAll(this)
    }

    private fun notify(id: Int, n: Notification) =
        getSystemService(NotificationManager::class.java).notify(id, n)

    private fun openApp() = PendingIntent.getActivity(
        this, 0, Intent(this, MainActivity::class.java),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    private fun base() = NotificationCompat.Builder(this, CHANNEL)
        .setSmallIcon(R.drawable.ic_rec)
        .setColor(getColor(R.color.accent))
        .setContentIntent(openApp())

    private fun ongoingNotification(): Notification = base()
        .setContentTitle(if (recorder != null) "녹음 중" else "준비 중")
        .setContentText("회의 속기록 — 멈추면 전사·요약까지 이어집니다")
        .setUsesChronometer(recorder != null)
        .setOngoing(true)
        .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
        .addAction(0, "정지", RecWidget.togglePending(this))
        .build()

    private fun resultNotification(ok: Boolean): Notification = base()
        .setContentTitle(if (ok) "녹음 올림 — 전사·요약 중" else "업로드 실패")
        .setContentText(if (ok) "잠시 뒤 요약이 기록에 뜹니다"
                        else "로그인·네트워크를 확인하세요. 다음 녹음 때 다시 보냅니다")
        .setAutoCancel(true)
        .build()

    private fun toast(msg: String) =
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
}
