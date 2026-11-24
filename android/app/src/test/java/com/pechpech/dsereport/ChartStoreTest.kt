package com.pechpech.dsereport

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.io.IOException
import java.time.Instant

class ChartStoreTest {
    @get:Rule val tmp = TemporaryFolder()

    private val base = "https://pech-pech.github.io/dse-report/v1/latest.json"
    private val fetched = mutableListOf<String>()

    private fun chart(date: String = "2026-11-23", code: String = "BXPHARMA", schema: Int = 1) = JSONObject()
        .put("schema", schema).put("code", code).put("asOf", date).put("sector", "Pharma").put("reading", "x")
        .toString()

    /** A store whose network answers with [answer] (a body, or throws) and records every URL asked for. */
    private fun store(dir: File = tmp.newFolder("r"), answer: (String) -> String = { chart() }) =
        ChartStore(dir, base) { url -> fetched += url; answer(url) }

    private fun saved(s: ChartStore, date: String = "2026-11-23", code: String = "BXPHARMA") =
        File(s.dir, "charts/$date/$code.json")

    @Test fun `bad dates and codes are not found and never fetched`() {
        val s = store()
        for (path in listOf("/charts/2026-1-23/BXPHARMA.json", "/charts/../BXPHARMA.json", "/charts/2026-11-23/bxpharma.json",
            "/charts/2026-11-23/.HIDDEN.json", "/charts/2026-11-23/BXPHARMA.txt", "/charts/2026-11-23/BXPHARMA",
            "/charts/2026-11-23/A/B.json", "/charts/2026-11-23/${"A".repeat(21)}.json", "/charts/2026-11-23/..json",
            "/charts/2026-11-23x/BXPHARMA.json", "/data/2026-11-23/BXPHARMA.json")) {
            assertTrue(path, s.serve(path) is ChartStore.Result.NotFound)
        }
        assertEquals(emptyList<String>(), fetched)
    }

    @Test fun `a saved chart is served without fetching`() {
        val s = store()
        saved(s).apply { parentFile!!.mkdirs(); writeText(chart()) }
        val r = s.serve("/charts/2026-11-23/BXPHARMA.json")
        assertArrayEquals(chart().toByteArray(), (r as ChartStore.Result.Ok).bytes)
        assertEquals(emptyList<String>(), fetched)
    }

    @Test fun `a missing chart is downloaded from pages once and saved`() {
        val s = store()
        val r = s.serve("/charts/2026-11-23/BXPHARMA.json")
        assertArrayEquals(chart().toByteArray(), (r as ChartStore.Result.Ok).bytes)
        assertEquals(listOf("https://pech-pech.github.io/dse-report/v1/charts/2026-11-23/BXPHARMA.json"), fetched)
        assertEquals(chart(), saved(s).readText())
        assertTrue(s.serve("/charts/2026-11-23/BXPHARMA.json") is ChartStore.Result.Ok)
        assertEquals(1, fetched.size)
        assertEquals(listOf("BXPHARMA.json"), saved(s).parentFile!!.list()!!.toList())   // no temp file left
    }

    @Test fun `codes with dots and dashes are allowed`() {
        val s = store { chart(code = "1STPRIMFMF-A.B") }
        assertTrue(s.get("2026-11-23", "1STPRIMFMF-A.B") is ChartStore.Result.Ok)
    }

    @Test fun `an invalid or mismatched body is not found and not saved`() {
        for (bad in listOf("", "{", "[]", "<html>", chart(schema = 2), chart(code = "SQURPHARMA"),
            chart(date = "2026-11-20"), JSONObject(chart()).apply { remove("schema") }.toString(),
            chart().dropLast(1) + ",\"pad\":\"" + "x".repeat(ChartStore.MAX_BYTES) + "\"}")) {
            val s = store(tmp.newFolder()) { bad }
            assertTrue(bad.take(30), s.serve("/charts/2026-11-23/BXPHARMA.json") is ChartStore.Result.NotFound)
            assertFalse(bad.take(30), saved(s).exists())
        }
    }

    @Test fun `pages answering 404 or a too large body is not found`() {
        val s404 = store(tmp.newFolder()) { throw HttpStatusException(404) }
        assertTrue(s404.get("2026-11-23", "BXPHARMA") is ChartStore.Result.NotFound)
        val big = store(tmp.newFolder()) { throw TooLargeException() }
        assertTrue(big.get("2026-11-23", "BXPHARMA") is ChartStore.Result.NotFound)
    }

    @Test fun `no connection or a server error is offline and saves nothing`() {
        for (e in listOf(IOException("timeout"), java.net.UnknownHostException("x"), HttpStatusException(503))) {
            val s = store(tmp.newFolder()) { throw e }
            assertTrue(e.toString(), s.get("2026-11-23", "BXPHARMA") is ChartStore.Result.Offline)
            assertFalse(File(s.dir, "charts").exists())
        }
    }

    @Test fun `the fetcher's typed errors keep their old messages`() {
        assertEquals("HTTP 404", HttpStatusException(404).message)
        assertEquals("report too large", TooLargeException().message)
    }

    @Test fun `charts are pruned with their report`() {
        val dir = tmp.newFolder("reports")
        val reports = ReportStore(dir, clock = { Instant.parse("2026-11-18T11:05:00Z") })
        val days = (1..ReportStore.KEEP + 2).map { "2026-10-%02d".format(it) }
        val s = store(dir) { url -> chart(date = url.split("/").let { it[it.size - 2] }) }
        // a chart for the oldest day, then reports through the newest: the first two days drop out
        days.forEach { day ->
            s.get(day, "BXPHARMA")
            reports.save(report(day))
        }
        assertFalse(File(dir, "charts/2026-10-01").exists())
        assertFalse(File(dir, "charts/2026-10-02").exists())
        assertTrue(saved(s, "2026-10-03").exists())
        assertTrue(saved(s, days.last()).exists())
    }

    private fun report(asOf: String) = JSONObject()
        .put("schema", 1).put("asOf", asOf)
        .put("periods", JSONObject().put("day", JSONObject()).put("week", JSONObject()).put("month", JSONObject()))
        .put("notification", JSONObject().put("title", "DSEX").put("lines", org.json.JSONArray()))
        .toString()
}
