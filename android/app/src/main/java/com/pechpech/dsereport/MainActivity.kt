package com.pechpech.dsereport

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat
import androidx.work.WorkInfo
import androidx.work.WorkManager

/**
 * One WebView showing the bundled card UI (assets/ui) and the saved report (files/reports), both through
 * WebViewAssetLoader on https://appassets.androidplatform.net, plus stock charts at /charts/ (ChartStore:
 * saved copy, else downloaded once). No file or content access, no JavaScript
 * bridge, no navigation off that origin: https links open in the browser, anything else is dropped.
 */
class MainActivity : Activity() {

    private lateinit var web: WebView
    private lateinit var loader: WebViewAssetLoader
    private lateinit var charts: ChartStore

    @SuppressLint("SetJavaScriptEnabled")   // the bundled UI is the only script the WebView ever runs
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Notifier.ensureChannel(this)
        DailyWorker.schedule(this)
        val reports = Paths.reports(this).apply { mkdirs() }
        loader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))   // /assets/ui/... -> assets/ui/...
            .addPathHandler("/data/", WebViewAssetLoader.InternalStoragePathHandler(this, reports))
            .build()
        charts = ChartStore(reports) { url -> ReportFetcher.fetch(url, ChartStore.MAX_BYTES) }
        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true          // the remembered Day/Week/Month choice
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.setSupportMultipleWindows(false)  // target=_blank comes back through shouldOverrideUrlLoading
            settings.javaScriptCanOpenWindowsAutomatically = false
            settings.setGeolocationEnabled(false)
            settings.mediaPlaybackRequiresUserGesture = true
            webViewClient = Client()
        }
        setContentView(web)
        if (savedInstanceState == null) load(intent) else web.restoreState(savedInstanceState)
        askNotificationPermission()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        load(intent)
    }

    override fun onResume() {
        super.onResume()
        val req = DailyWorker.fetchNow(this)
        WorkManager.getInstance(this).getWorkInfoByIdLiveData(req.id).observeForever(object :
            androidx.lifecycle.Observer<WorkInfo?> {
            override fun onChanged(value: WorkInfo?) {
                if (value == null || !value.state.isFinished) return
                WorkManager.getInstance(this@MainActivity).getWorkInfoByIdLiveData(req.id).removeObserver(this)
                if (value.outputData.getBoolean(DailyWorker.KEY_NEW, false) && !isFinishing) web.reload()
            }
        })
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    /** Back closes an open write-up sheet first (the page answers true), then leaves the app. */
    @Deprecated("Activity back handling")
    override fun onBackPressed() {
        web.evaluateJavascript("!!(window.DSEReport && window.DSEReport.back())") { handled ->
            if (handled != "true" && !isFinishing) {
                @Suppress("DEPRECATION")
                super.onBackPressed()
            }
        }
    }

    override fun onDestroy() {
        web.destroy()
        super.onDestroy()
    }

    private fun load(intent: Intent?) {
        val card = intent?.getIntExtra(Notifier.EXTRA_CARD, 0) ?: 0
        web.loadUrl(START + if (card > 0) "#card=$card" else "")
    }

    private fun askNotificationPermission() {
        if (Build.VERSION.SDK_INT < 33) return
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) return
        val prefs = getSharedPreferences("app", MODE_PRIVATE)
        if (prefs.getBoolean("asked_notifications", false)) return
        prefs.edit().putBoolean("asked_notifications", true).apply()
        requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
    }

    private inner class Client : WebViewClientCompat() {
        override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
            if (request.url.host != HOST) return blocked()
            // a stock's chart: the saved copy, else downloaded once (this runs off the main thread)
            if (request.url.path.orEmpty().startsWith("/charts/")) return chart(request.url.path.orEmpty())
            val r = loader.shouldInterceptRequest(request.url)
            // a missing file (no report saved yet) is a plain 404, which the page handles
            return if (r == null || r.data == null) notFound() else r
        }

        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val url = request.url
            if (url.scheme == "https" && url.host == HOST) return false
            if (url.scheme == "https" && request.hasGesture()) openOutside(url)
            return true
        }
    }

    private fun chart(path: String): WebResourceResponse = when (val r = charts.serve(path)) {
        is ChartStore.Result.Ok -> WebResourceResponse("application/json", "utf-8", 200, "OK", emptyMap(), r.bytes.inputStream())
        ChartStore.Result.NotFound -> notFound()
        ChartStore.Result.Offline -> unavailable()
    }

    private fun openOutside(url: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, url).addCategory(Intent.CATEGORY_BROWSABLE))
        } catch (_: ActivityNotFoundException) {
            // no browser: nothing to do
        }
    }

    companion object {
        private const val HOST = "appassets.androidplatform.net"
        private const val START = "https://$HOST/assets/ui/index.html"
        // any request off the app origin (the page has a strict CSP; this is the second lock)
        private fun blocked() = WebResourceResponse("text/plain", "utf-8", 403, "Blocked", emptyMap(), ByteArray(0).inputStream())
        private fun notFound() = WebResourceResponse("text/plain", "utf-8", 404, "Not Found", emptyMap(), ByteArray(0).inputStream())
        // a chart that could not be downloaded and was never saved (the page offers Try again)
        private fun unavailable() = WebResourceResponse("text/plain", "utf-8", 503, "Service Unavailable", emptyMap(), ByteArray(0).inputStream())
    }
}
