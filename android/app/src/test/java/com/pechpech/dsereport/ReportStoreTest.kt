package com.pechpech.dsereport

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.time.Instant

class ReportStoreTest {
    @get:Rule val tmp = TemporaryFolder()

    private fun report(asOf: String, title: String = "DSEX +0.61% · 23 buys · 4 sells") = JSONObject()
        .put("schema", 1).put("asOf", asOf)
        .put("periods", JSONObject().put("day", JSONObject()).put("week", JSONObject()).put("month", JSONObject()))
        .put("notification", JSONObject().put("title", title).put("lines", org.json.JSONArray(listOf("a", "", "b"))))
        .toString()

    private fun store() = ReportStore(tmp.newFolder("r"), clock = { Instant.parse("2026-11-18T11:05:00Z") })

    @Test fun `fixture from the live site passes the check`() {
        val f = File("../ui-test/fixtures/latest.json")
        val c = ReportStore.check(f.readText())!!
        assertEquals("2026-11-17", c.asOf)
        assertTrue(c.title.startsWith("DSEX"))
    }

    @Test fun `new report is saved with its dated copy and meta`() {
        val s = store()
        val (outcome, c) = s.save(report("2026-11-17"))
        assertEquals(ReportStore.Outcome.NEW, outcome)
        assertEquals(listOf("a", "b"), c!!.lines)
        assertTrue(File(s.dir, "2026-11-17.json").exists())
        assertEquals("2026-11-17", s.latestAsOf)
        val meta = JSONObject(File(s.dir, "meta.json").readText())
        assertEquals("2026-11-18T11:05:00Z", meta.getString("savedAt"))
        assertFalse(meta.getBoolean("offline"))
    }

    @Test fun `same or older session is not new and does not replace the saved one`() {
        val s = store()
        s.save(report("2026-11-17"))
        assertEquals(ReportStore.Outcome.SAME, s.save(report("2026-11-17")).first)
        assertEquals(ReportStore.Outcome.SAME, s.save(report("2026-11-16")).first)
        assertEquals("2026-11-17", s.latestAsOf)
    }

    @Test fun `bad bodies are rejected and leave the saved report alone`() {
        val s = store()
        s.save(report("2026-11-17"))
        for (bad in listOf("", "{", "[]", report("2026-11-18").replace("\"schema\":1", "\"schema\":2"),
            report("18-11-2026"), report("2026-11-18", title = ""),
            JSONObject(report("2026-11-18")).apply { remove("periods") }.toString(),
            "x".repeat(ReportStore.MAX_BYTES + 1))) {
            assertEquals(bad.take(30), ReportStore.Outcome.INVALID, s.save(bad).first)
        }
        assertEquals("2026-11-17", s.latestAsOf)
        assertFalse(JSONObject(File(s.dir, "meta.json").readText()).isNull("error"))
    }

    @Test fun `only the newest thirty sessions are kept`() {
        val s = store()
        val days = (1..35).map { "2026-10-%02d".format(it) }
        days.forEach { s.save(report(it)) }
        val kept = s.dir.listFiles()!!.map { it.name }.filter { it.matches(Regex("""\d{4}-\d{2}-\d{2}\.json""")) }
        assertEquals(ReportStore.KEEP, kept.size)
        assertFalse("2026-10-05.json" in kept)
        assertTrue("2026-10-06.json" in kept)
    }

    @Test fun `offline keeps the last saved time`() {
        val s = store()
        s.save(report("2026-11-17"))
        s.markOffline("Could not reach the report")
        val meta = JSONObject(File(s.dir, "meta.json").readText())
        assertTrue(meta.getBoolean("offline"))
        assertEquals("2026-11-18T11:05:00Z", meta.getString("savedAt"))
    }

    @Test fun `offline before anything was saved has no time`() {
        val s = store()
        s.markOffline("x")
        assertTrue(JSONObject(File(s.dir, "meta.json").readText()).isNull("savedAt"))
        assertNull(s.latestAsOf)
    }
}
