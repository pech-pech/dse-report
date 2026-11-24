package com.pechpech.dsereport

import java.io.IOException
import java.net.URL
import javax.net.ssl.HttpsURLConnection

/** A non-200 answer; still an IOException ("HTTP <code>"), so existing callers see no change. */
class HttpStatusException(val code: Int) : IOException("HTTP $code")

/** A body over the size cap; still an IOException with the old message. */
class TooLargeException : IOException("report too large")

/** One HTTPS GET of the published report (or a chart: [maxBytes]), size-capped, no redirects. */
object ReportFetcher {
    private const val TIMEOUT_MS = 20_000

    fun fetch(url: String = BuildConfig.REPORT_URL, maxBytes: Int = ReportStore.MAX_BYTES): String {
        val conn = URL(url).openConnection() as? HttpsURLConnection ?: throw IOException("not https")
        try {
            conn.connectTimeout = TIMEOUT_MS
            conn.readTimeout = TIMEOUT_MS
            conn.instanceFollowRedirects = false
            conn.setRequestProperty("Accept", "application/json")
            conn.useCaches = false
            val code = conn.responseCode
            if (code != 200) throw HttpStatusException(code)
            conn.inputStream.use { input ->
                val buf = java.io.ByteArrayOutputStream()
                val chunk = ByteArray(16 * 1024)
                while (true) {
                    val n = input.read(chunk)
                    if (n < 0) break
                    buf.write(chunk, 0, n)
                    if (buf.size() > maxBytes) throw TooLargeException()
                }
                return buf.toString(Charsets.UTF_8.name())
            }
        } finally {
            conn.disconnect()
        }
    }
}
