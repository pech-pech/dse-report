package com.pechpech.dsereport

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId
import java.time.ZonedDateTime

class ScheduleTest {
    private val dhaka = ZoneId.of("Asia/Dhaka")
    private fun at(y: Int, m: Int, d: Int, h: Int, min: Int = 0) = ZonedDateTime.of(y, m, d, h, min, 0, 0, dhaka)

    @Test fun `next run is the next 15_15 or 17_10 on a trading day`() {
        assertEquals(at(2026, 11, 23, 15, 15), DailyWorker.nextRun(at(2026, 11, 23, 10)))      // Monday morning
        assertEquals(at(2026, 11, 23, 17, 10), DailyWorker.nextRun(at(2026, 11, 23, 15, 15)))  // just after the first
        assertEquals(at(2026, 11, 24, 15, 15), DailyWorker.nextRun(at(2026, 11, 23, 18)))      // evening: tomorrow
    }

    @Test fun `next run skips Friday and Saturday`() {
        assertEquals(at(2026, 11, 22, 15, 15), DailyWorker.nextRun(at(2026, 11, 19, 18)))      // Thursday -> Sunday
        assertEquals(at(2026, 11, 22, 15, 15), DailyWorker.nextRun(at(2026, 11, 21, 16)))      // Saturday -> Sunday
    }

    @Test fun `retry only while today's report is still missing, on a trading day from 15_00 to 21_00`() {
        assertTrue(DailyWorker.awaitingToday(at(2026, 11, 23, 15, 15), "2026-11-22"))
        assertTrue(DailyWorker.awaitingToday(at(2026, 11, 23, 20, 59), null))
        assertFalse(DailyWorker.awaitingToday(at(2026, 11, 23, 15, 15), "2026-11-23"))  // already have today's
        assertFalse(DailyWorker.awaitingToday(at(2026, 11, 23, 14, 59), "2026-11-22"))
        assertFalse(DailyWorker.awaitingToday(at(2026, 11, 23, 21), "2026-11-22"))
        assertFalse(DailyWorker.awaitingToday(at(2026, 11, 20, 17), "2026-11-19"))       // Friday
        assertFalse(DailyWorker.awaitingToday(at(2026, 11, 21, 17), "2026-11-19"))       // Saturday
    }
}
