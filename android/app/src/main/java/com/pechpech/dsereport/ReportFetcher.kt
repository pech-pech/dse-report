package com.pechpech.dsereport

import java.io.IOException
import java.net.URL
import javax.net.ssl.HttpsURLConnection

/** One HTTPS GET of the published report, size-capped. */
object ReportFetcher {
    private const val TIMEOUT_MS = 20_000

    fun fetch(url: String = BuildConfig.REPORT_URL): String {
        val conn = URL(url).openConnection() as? HttpsURLConnection ?: throw IOException("not https")
        try {
            conn.connectTimeout = TIMEOUT_MS
            conn.readTimeout = TIMEOUT_MS
            conn.instanceFollowRedirects = false
            conn.setRequestProperty("Accept", "application/json")
            conn.useCaches = false
            val code = conn.responseCode
            if (code != 200) throw IOException("HTTP $code")
            conn.inputStream.use { input ->
                val buf = java.io.ByteArrayOutputStream()
                val chunk = ByteArray(16 * 1024)
                while (true) {
                    val n = input.read(chunk)
                    if (n < 0) break
                    buf.write(chunk, 0, n)
                    if (buf.size() > ReportStore.MAX_BYTES) throw IOException("report too large")
                }
                return buf.toString(Charsets.UTF_8.name())
            }
        } finally {
            conn.disconnect()
        }
    }
}
