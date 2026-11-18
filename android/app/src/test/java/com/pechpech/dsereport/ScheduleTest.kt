package com.pechpech.dsereport

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Duration
import java.time.ZoneId
import java.time.ZonedDateTime

class ScheduleTest {
    private val dhaka = ZoneId.of("Asia/Dhaka")
    private fun at(y: Int, m: Int, d: Int, h: Int, min: Int = 0) = ZonedDateTime.of(y, m, d, h, min, 0, 0, dhaka)

    @Test fun `next run is 17_05 today before it and tomorrow after it`() {
        assertEquals(Duration.ofMinutes(65), DailyWorker.delayToNextRun(at(2026, 11, 18, 16)))
        assertEquals(Duration.ofHours(24).minusMinutes(55), DailyWorker.delayToNextRun(at(2026, 11, 18, 18)))
    }

    @Test fun `waiting for today's report only on trading days in the evening`() {
        assertTrue(DailyWorker.awaitingToday(at(2026, 11, 18, 17)))        // Wednesday
        assertFalse(DailyWorker.awaitingToday(at(2026, 11, 18, 21)))
        assertFalse(DailyWorker.awaitingToday(at(2026, 11, 18, 10)))
        assertFalse(DailyWorker.awaitingToday(at(2026, 11, 20, 17)))       // Friday
        assertFalse(DailyWorker.awaitingToday(at(2026, 11, 21, 17)))       // Saturday
        assertTrue(DailyWorker.awaitingToday(at(2026, 11, 22, 17)))        // Sunday
    }
}
