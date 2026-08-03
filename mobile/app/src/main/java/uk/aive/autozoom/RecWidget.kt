package uk.aive.autozoom

import android.Manifest
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.widget.RemoteViews
import android.widget.Toast
import androidx.core.content.ContextCompat

/**
 * 홈 화면 1x1 녹음 위젯. 한 번 누르면 녹음 시작, 다시 누르면 정지 → 서버로 업로드.
 *
 * 서비스를 바로 띄우지 않고 이 리시버를 거치는 이유: 마이크 권한이 없는데 마이크 타입
 * 포그라운드 서비스를 띄우면 SecurityException 으로 죽는다. 권한은 위젯이 못 물어보니
 * 여기서 확인하고 없으면 앱을 열어 준다.
 */
class RecWidget : AppWidgetProvider() {

    override fun onUpdate(context: Context, mgr: AppWidgetManager, ids: IntArray) {
        ids.forEach { mgr.updateAppWidget(it, views(context)) }
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_TOGGLE) {
            super.onReceive(context, intent)
            return
        }
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
            Toast.makeText(context, "앱을 열어 마이크 권한을 허용해주세요", Toast.LENGTH_LONG).show()
            context.startActivity(Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return
        }
        ContextCompat.startForegroundService(
            context, Intent(context, RecService::class.java).setAction(ACTION_TOGGLE))
    }

    companion object {
        const val ACTION_TOGGLE = RecService.ACTION_TOGGLE
        const val IDLE = "idle"
        const val REC = "rec"
        const val UP = "up"

        fun togglePending(context: Context): PendingIntent = PendingIntent.getBroadcast(
            context, 0,
            Intent(context, RecWidget::class.java).setAction(ACTION_TOGGLE),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

        private fun views(context: Context): RemoteViews {
            val (glyph, label, color) = when (RecService.state) {
                REC -> Triple("■", "녹음 중", R.color.accent)
                UP -> Triple("↑", "전송 중", R.color.ink_2)
                else -> Triple("●", "녹음", R.color.ink_2)
            }
            return RemoteViews(context.packageName, R.layout.widget_rec).apply {
                setTextViewText(R.id.dot, glyph)
                setTextViewText(R.id.label, label)
                setTextColor(R.id.dot, context.getColor(color))
                setOnClickPendingIntent(R.id.widget_root, togglePending(context))
            }
        }

        /** 상태가 바뀔 때마다 홈에 붙어 있는 위젯을 전부 다시 그린다. */
        fun renderAll(context: Context) {
            val mgr = AppWidgetManager.getInstance(context)
            val ids = mgr.getAppWidgetIds(ComponentName(context, RecWidget::class.java))
            if (ids.isNotEmpty()) mgr.updateAppWidget(ids, views(context))
        }
    }
}
