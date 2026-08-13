package uk.aive.autozoom

import android.Manifest
import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Color
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import uk.aive.autozoom.databinding.ActivityMainBinding

/**
 * autozoom.ai-ve.uk 회의 속기록을 감싸는 WebView 셸.
 *
 * 의도적으로 **얇게** 짰다 — 화면·기능은 전부 서버의 app/ui.py 에서 오므로, 웹을 고치면
 * 앱을 다시 빌드하지 않아도 그대로 반영된다. 앱이 더하는 건 껍데기뿐이다:
 * 당겨서 새로고침 · 상단 진행바 · 오프라인 화면 · 뒤로가기 2번 종료 · 외부링크 분리.
 *
 * 로그인은 서버 세션 쿠키(az_session, 14일)로 유지된다 — 앱은 그 쿠키만 디스크에 붙들어 둔다
 * (onPause 의 flush). 앱 안에 계정 정보를 저장하는 부분은 없다.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private var isPageLoaded = false

    private var lastBackPressTime: Long = 0L
    private var backPressToast: Toast? = null

    /** 위젯은 권한을 물어볼 수 없다 — 마이크·알림 권한은 앱이 떠 있을 때 미리 받아 둔다. */
    private val askPermissions =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { }

    /** 웹의 '동영상 올리기' 탭이 연 파일 선택창. 취소해도 null 을 돌려줘야 웹뷰가 풀린다. */
    private var pendingFilePick: ValueCallback<Array<Uri>>? = null
    private val pickFile =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            pendingFilePick?.onReceiveValue(
                WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data))
            pendingFilePick = null
        }

    companion object {
        private const val WEB_URL = "https://autozoom.ai-ve.uk"
        private const val HOST = "autozoom.ai-ve.uk"
        private const val KEY_URL = "current_url"
        private const val BACK_EXIT_WINDOW_MS = 2000L
    }

    // 색은 res 에서 읽는다 — values/ 와 values-night/ 가 갈라주므로 여기서 분기하지 않는다.
    private val paper get() = getColor(R.color.paper)
    private val accent get() = getColor(R.color.accent)
    private val isNight get() =
        resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK ==
            Configuration.UI_MODE_NIGHT_YES

    override fun onCreate(savedInstanceState: Bundle?) {
        val splashScreen = installSplashScreen()
        splashScreen.setKeepOnScreenCondition { !isPageLoaded }

        super.onCreate(savedInstanceState)
        setupEdgeToEdge()

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        applySystemBarInsets()

        setupWebView()
        setupPullToRefresh()
        setupBackNavigation()
        requestRecordingPermissions()
        binding.btnRetry.setOnClickListener {
            if (isNetworkAvailable()) { hideErrorState(); loadUrl(WEB_URL) }
        }

        val urlToLoad = savedInstanceState?.getString(KEY_URL) ?: WEB_URL
        if (isNetworkAvailable()) loadUrl(urlToLoad) else showErrorState()
    }

    private fun setupEdgeToEdge() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = paper
        WindowInsetsControllerCompat(window, window.decorView).apply {
            // 종이 배경(밝은 모드)엔 어두운 아이콘이 필요하다 — 안 뒤집으면 흰 위에 흰색이 된다.
            isAppearanceLightStatusBars = !isNight
            isAppearanceLightNavigationBars = !isNight
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)
    }

    /**
     * edge-to-edge 를 켰으면 누군가는 인셋을 소비해야 한다 — 아무도 안 하면 WebView 가 상태바
     * 아래로 파고들어 대시보드 헤더가 시계·배터리와 겹친다. 루트에 패딩으로 물려 WebView·
     * 프로그레스바·에러화면이 한꺼번에 시스템 바(+노치)를 피하게 한다.
     */
    private fun applySystemBarInsets() {
        ViewCompat.setOnApplyWindowInsetsListener(binding.root) { v, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        ViewCompat.requestApplyInsets(binding.root)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        binding.webView.apply {
            setBackgroundColor(paper)
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                useWideViewPort = true
                loadWithOverviewMode = true
                setSupportZoom(false)
                builtInZoomControls = false
                displayZoomControls = false
                cacheMode = WebSettings.LOAD_DEFAULT
                userAgentString = "$userAgentString AutoZoomApp/1.0"
                mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            }
            CookieManager.getInstance().let {
                it.setAcceptCookie(true)
                it.setAcceptThirdPartyCookies(this, true)
            }
            webViewClient = AppWebViewClient()
            webChromeClient = AppChromeClient()
            isVerticalScrollBarEnabled = false
            isHorizontalScrollBarEnabled = false
            overScrollMode = View.OVER_SCROLL_NEVER
        }
    }


    /**
     * 당겨서 새로고침. 목록은 진행 중인 회의가 있을 때만 10초마다 자동 갱신되므로, 그 밖에는
     * 사용자가 직접 당겨야 한다. **웹뷰가 최상단일 때만** 켠다 — 아니면 기록 표를 위로
     * 스크롤하려는 제스처가 매번 새로고침으로 먹힌다.
     */
    private fun setupPullToRefresh() {
        binding.swipeRefresh.apply {
            setColorSchemeColors(accent)
            setProgressBackgroundColorSchemeColor(getColor(R.color.rule))
            setOnRefreshListener { binding.webView.reload() }
        }
        binding.webView.setOnScrollChangeListener { _, _, scrollY, _, _ ->
            binding.swipeRefresh.isEnabled = scrollY == 0
        }
    }

    private fun hasMic() = ContextCompat.checkSelfPermission(
        this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun requestRecordingPermissions() {
        val need = mutableListOf<String>()
        if (!hasMic()) need += Manifest.permission.RECORD_AUDIO
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(
                this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            need += Manifest.permission.POST_NOTIFICATIONS
        }
        if (need.isNotEmpty()) askPermissions.launch(need.toTypedArray())
    }

    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (binding.webView.canGoBack()) { binding.webView.goBack(); return }
                val now = System.currentTimeMillis()
                if (now - lastBackPressTime <= BACK_EXIT_WINDOW_MS) {
                    backPressToast?.cancel(); finish(); return
                }
                lastBackPressTime = now
                backPressToast?.cancel()
                backPressToast = Toast.makeText(
                    this@MainActivity, "한 번 더 누르면 종료됩니다", Toast.LENGTH_SHORT
                ).also { it.show() }
            }
        })
    }

    private fun loadUrl(url: String) {
        binding.errorContainer.visibility = View.GONE
        binding.webView.visibility = View.VISIBLE
        binding.webView.loadUrl(url)
    }

    private fun showErrorState() {
        binding.webView.visibility = View.GONE
        binding.errorContainer.visibility = View.VISIBLE
        binding.progressBar.visibility = View.GONE
        binding.swipeRefresh.isRefreshing = false
    }

    private fun hideErrorState() {
        binding.errorContainer.visibility = View.GONE
        binding.webView.visibility = View.VISIBLE
    }

    private fun isNetworkAvailable(): Boolean {
        val cm = getSystemService(ConnectivityManager::class.java)
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    /** 세션 쿠키를 디스크에 확정한다 — 안 하면 앱이 강제 종료될 때 로그인이 풀린다. */
    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putString(KEY_URL, binding.webView.url)
        binding.webView.saveState(outState)
    }

    override fun onRestoreInstanceState(savedInstanceState: Bundle) {
        super.onRestoreInstanceState(savedInstanceState)
        binding.webView.restoreState(savedInstanceState)
    }

    inner class AppWebViewClient : WebViewClient() {
        override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
            super.onPageStarted(view, url, favicon)
            binding.progressBar.visibility = View.VISIBLE
        }

        override fun onPageFinished(view: WebView?, url: String?) {
            super.onPageFinished(view, url)
            isPageLoaded = true
            binding.progressBar.visibility = View.GONE
            binding.swipeRefresh.isRefreshing = false
            CookieManager.getInstance().flush()
        }

        override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
            val url = request?.url?.toString() ?: return false
            if (url.contains(HOST)) return false
            try {                                   // 외부 링크는 시스템 브라우저로
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
            } catch (_: Exception) { /* 핸들러 없는 URL 무시 */ }
            return true
        }

        override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
            super.onReceivedError(view, request, error)
            if (request?.isForMainFrame == true) showErrorState()
        }
    }

    inner class AppChromeClient : WebChromeClient() {
        override fun onProgressChanged(view: WebView?, newProgress: Int) {
            super.onProgressChanged(view, newProgress)
            binding.progressBar.progress = newProgress
            if (newProgress >= 100) binding.progressBar.visibility = View.GONE
        }

        /**
         * 웹의 `<input type=file>` 에 안드로이드 파일 선택창을 붙인다. 이걸 안 달면 '동영상
         * 올리기' 탭의 파일 고르기가 앱 안에서 아무 반응 없이 죽는다(웹 기본값은 거절).
         */
        override fun onShowFileChooser(
            view: WebView?,
            callback: ValueCallback<Array<Uri>>,
            params: FileChooserParams,
        ): Boolean {
            pendingFilePick?.onReceiveValue(null)   // 앞선 요청이 떠 있으면 먼저 풀어 준다
            pendingFilePick = callback
            return try {
                pickFile.launch(params.createIntent())
                true
            } catch (e: ActivityNotFoundException) {
                pendingFilePick = null
                Toast.makeText(this@MainActivity, "파일을 고를 앱이 없습니다.",
                    Toast.LENGTH_SHORT).show()
                false
            }
        }

        /** 웹의 '직접 녹음' 버튼(getUserMedia)에 마이크를 내준다 — 앱이 이미 받은 권한 한도 안에서만. */
        override fun onPermissionRequest(request: PermissionRequest) {
            val mic = PermissionRequest.RESOURCE_AUDIO_CAPTURE
            if (request.resources.contains(mic) && hasMic()) {
                request.grant(arrayOf(mic))
            } else {
                request.deny()
                requestRecordingPermissions()
            }
        }
    }
}
