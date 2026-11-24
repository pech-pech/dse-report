package com.pechpech.dsereport

import org.json.JSONObject
import java.io.File
import java.io.IOException

/**
 * One stock's chart for one report day, for the page's /charts/<date>/<CODE>.json. Served from the saved copy
 * (files/reports/charts/<date>/<CODE>.json) when there is one, else downloaded once from GitHub Pages, checked,
 * saved and served. ReportStore deletes a day's charts with its report. [fetch] is one HTTPS GET of a URL
 * (ReportFetcher.fetch in the app, a fake in tests): HttpStatusException(404) means the chart is not published.
 */
class ChartStore(
    val dir: File,                                  // the reports dir; charts live in its charts/ folder
    private val reportUrl: String = BuildConfig.REPORT_URL,
    private val fetch: (String) -> String,
) {

    sealed class Result {
        class Ok(val bytes: ByteArray) : Result()
        object NotFound : Result()   // bad path, not published, or not a valid chart
        object Offline : Result()    // could not download and nothing saved
    }

    /** A page path "/charts/<date>/<CODE>.json"; anything else is NotFound without touching the network. */
    fun serve(path: String): Result {
        val parts = path.removePrefix("/").split("/")
        if (parts.size != 3 || parts[0] != DIR || !parts[2].endsWith(".json")) return Result.NotFound
        return get(parts[1], parts[2].removeSuffix(".json"))
    }

    fun get(date: String, code: String): Result {
        if (!DATE.matches(date) || !CODE.matches(code)) return Result.NotFound
        val saved = File(File(File(dir, DIR), date), "$code.json")
        if (saved.isFile) runCatching { return Result.Ok(saved.readBytes()) }
        val url = reportUrl.substringBeforeLast('/') + "/$DIR/$date/$code.json"
        if (!url.startsWith("https://")) return Result.Offline
        val body = try {
            fetch(url)
        } catch (e: HttpStatusException) {
            return if (e.code == 404) Result.NotFound else Result.Offline   // a 5xx is Pages being down
        } catch (_: TooLargeException) {
            return Result.NotFound
        } catch (_: IOException) {
            return Result.Offline
        }
        val bytes = body.toByteArray(Charsets.UTF_8)
        if (!valid(body, bytes.size, date, code)) return Result.NotFound
        // a failed save still serves this once; the next open downloads again
        runCatching { atomicWrite(saved, bytes) }
        return Result.Ok(bytes)
    }

    /** Write to a unique temp file beside the target, then rename: a reader never sees half a chart. */
    private fun atomicWrite(target: File, bytes: ByteArray) {
        target.parentFile!!.mkdirs()
        val tmp = File.createTempFile(target.name, ".tmp", target.parentFile)
        try {
            tmp.writeBytes(bytes)
            if (!tmp.renameTo(target)) throw IOException("could not save ${target.name}")
        } finally {
            tmp.delete()   // no-op after a successful rename
        }
    }

    companion object {
        const val DIR = "charts"
        const val SCHEMA = 1
        const val MAX_BYTES = 1_000_000
        val DATE = Regex("""\d{4}-\d{2}-\d{2}""")
        val CODE = Regex("""[A-Z0-9][A-Z0-9._-]{0,19}""")

        /** The fields the shell relies on (the page checks the rest): a v1 chart for exactly this path. */
        fun valid(body: String, size: Int, date: String, code: String): Boolean {
            if (size > MAX_BYTES) return false
            val o = runCatching { JSONObject(body) }.getOrNull() ?: return false
            return o.optInt("schema", -1) == SCHEMA && o.optString("code") == code && o.optString("asOf") == date
        }
    }
}
