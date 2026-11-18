package com.pechpech.dsereport

import org.json.JSONObject
import java.io.File
import java.time.Instant

/**
 * The saved reports, in the app's private files: latest.json (what the page shows), one file per session
 * (the newest [KEEP] kept) and meta.json (saved time, offline flag, last error). The page reads them through
 * WebViewAssetLoader at /data/; nothing else reads or writes them.
 */
class ReportStore(val dir: File, private val clock: () -> Instant = Instant::now) {

    enum class Outcome { NEW, SAME, INVALID }

    data class Checked(val asOf: String, val title: String, val lines: List<String>)

    init {
        dir.mkdirs()
    }

    val latestAsOf: String?
        get() = runCatching { JSONObject(File(dir, LATEST).readText()).getString("asOf") }.getOrNull()

    /** Validate and save a downloaded report. NEW only when its session is newer than the saved one. */
    fun save(body: String): Pair<Outcome, Checked?> {
        val checked = check(body) ?: run {
            writeMeta(offline = false, error = "The downloaded report was not readable")
            return Outcome.INVALID to null
        }
        val current = latestAsOf
        if (current != null && checked.asOf <= current) {
            writeMeta(offline = false, error = null)
            return Outcome.SAME to checked
        }
        atomicWrite(File(dir, "${checked.asOf}.json"), body)
        atomicWrite(File(dir, LATEST), body)
        prune()
        writeMeta(offline = false, error = null)
        return Outcome.NEW to checked
    }

    fun markOffline(error: String) = writeMeta(offline = true, error = error)

    private fun writeMeta(offline: Boolean, error: String?) {
        val old = runCatching { JSONObject(File(dir, META).readText()) }.getOrNull()
        val meta = JSONObject()
            .put("savedAt", if (offline) old?.opt("savedAt") ?: JSONObject.NULL else clock().toString())
            .put("offline", offline)
            .put("error", error ?: JSONObject.NULL)
        atomicWrite(File(dir, META), meta.toString())
    }

    private fun prune() {
        val dated = dir.listFiles { f -> DATED.matches(f.name) }?.sortedByDescending { it.name } ?: return
        dated.drop(KEEP).forEach { it.delete() }
    }

    private fun atomicWrite(target: File, text: String) {
        val tmp = File(dir, target.name + ".tmp")
        tmp.writeText(text)
        if (!tmp.renameTo(target)) {
            tmp.delete()
            throw java.io.IOException("could not save ${target.name}")
        }
    }

    companion object {
        const val LATEST = "latest.json"
        const val META = "meta.json"
        const val KEEP = 30
        const val SCHEMA = 1
        const val MAX_BYTES = 2_000_000
        private val DATED = Regex("""\d{4}-\d{2}-\d{2}\.json""")
        private val DATE = Regex("""\d{4}-\d{2}-\d{2}""")

        /** The fields the shell relies on; the page checks the rest. Null when the body is not a v1 report. */
        fun check(body: String): Checked? {
            if (body.length > MAX_BYTES) return null
            val o = runCatching { JSONObject(body) }.getOrNull() ?: return null
            if (o.optInt("schema", -1) != SCHEMA) return null
            val asOf = o.optString("asOf")
            if (!DATE.matches(asOf)) return null
            val periods = o.optJSONObject("periods") ?: return null
            if (listOf("day", "week", "month").any { periods.optJSONObject(it) == null }) return null
            val n = o.optJSONObject("notification") ?: return null
            val title = n.optString("title").take(120)
            if (title.isBlank()) return null
            val arr = n.optJSONArray("lines")
            val lines = (0 until (arr?.length() ?: 0)).map { arr!!.optString(it).take(160) }.filter { it.isNotBlank() }
            return Checked(asOf, title, lines.take(6))
        }
    }
}
