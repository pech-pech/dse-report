package com.pechpech.dsereport

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequest
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.DayOfWeek
import java.time.Duration
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.concurrent.TimeUnit

/**
 * Downloads the report, saves it, and notifies once per new session. The report is published about 15:02 Dhaka
 * and rebuilt about 16:57 with the complete end-of-day data; [DailyAlarm] wakes the app at [RUN_TIMES] (an
 * alarm, because WorkManager's periodic job can be put off for hours). This worker is the retry path and the
 * daily fallback: while today's report is still missing it retries with back-off until [LAST_TRY_HOUR].
 */
class DailyWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val notify = inputData.getBoolean(KEY_NOTIFY, true)
        when (ReportSync.run(applicationContext, notify)) {
            ReportSync.Result.NEW, ReportSync.Result.UPDATED -> Result.success(workDataOf(KEY_NEW to true))
            ReportSync.Result.SAME ->
                if (notify && awaitingToday(latest = ReportSync.latestAsOf(applicationContext)) &&
                    runAttemptCount < MAX_ATTEMPTS) Result.retry()
                else Result.success(workDataOf(KEY_NEW to false))
            ReportSync.Result.OFFLINE -> if (runAttemptCount < MAX_ATTEMPTS) Result.retry() else Result.failure()
            ReportSync.Result.INVALID -> Result.failure()
        }
    }

    companion object {
        const val KEY_NOTIFY = "notify"
        const val KEY_NEW = "new"
        private const val DAILY = "daily-report"
        const val NOW = "report-now"
        const val RETRY = "report-retry"
        private const val MAX_ATTEMPTS = 8
        private const val FIRST_TRY_HOUR = 15
        private const val LAST_TRY_HOUR = 21
        val DHAKA: ZoneId = ZoneId.of("Asia/Dhaka")
        /** After the 15:00 build (out about 15:02) and after the 16:55 rebuild (out about 16:57). */
        val RUN_TIMES: List<LocalTime> = listOf(LocalTime.of(15, 15), LocalTime.of(17, 10))
        private val TRADING = setOf(DayOfWeek.SUNDAY, DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY,
            DayOfWeek.THURSDAY)

        /** Trading day, between the first build and the last try, and today's session not saved yet. */
        fun awaitingToday(now: ZonedDateTime = ZonedDateTime.now(DHAKA), latest: String?): Boolean =
            now.dayOfWeek in TRADING && now.hour in FIRST_TRY_HOUR until LAST_TRY_HOUR &&
                (latest == null || latest < now.toLocalDate().toString())

        /** The next of [RUN_TIMES] on a trading day, strictly after [now]. */
        fun nextRun(now: ZonedDateTime = ZonedDateTime.now(DHAKA)): ZonedDateTime {
            val local = now.withZoneSameInstant(DHAKA)
            for (day in 0L..7L) {
                val date = local.toLocalDate().plusDays(day)
                if (date.dayOfWeek !in TRADING) continue
                RUN_TIMES.map { ZonedDateTime.of(date, it, DHAKA) }.firstOrNull { it.isAfter(local) }?.let { return it }
            }
            error("no trading day within a week")
        }

        private val network = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        /** The alarm plus the periodic fallback (kept in case alarms are blocked by a battery saver). */
        fun schedule(ctx: Context) {
            DailyAlarm.arm(ctx)
            val delay = Duration.between(ZonedDateTime.now(DHAKA), nextRun())
            val req = PeriodicWorkRequestBuilder<DailyWorker>(24, TimeUnit.HOURS)
                .setInitialDelay(delay.toMinutes(), TimeUnit.MINUTES)
                .setConstraints(network)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 15, TimeUnit.MINUTES)
                .build()
            WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(DAILY, ExistingPeriodicWorkPolicy.UPDATE, req)
        }

        /** Retry path after an alarm whose fetch found no new report or no network. */
        fun retrySoon(ctx: Context) {
            val req = OneTimeWorkRequestBuilder<DailyWorker>()
                .setInitialDelay(10, TimeUnit.MINUTES)
                .setConstraints(network)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 15, TimeUnit.MINUTES)
                .build()
            WorkManager.getInstance(ctx).enqueueUniqueWork(RETRY, ExistingWorkPolicy.KEEP, req)
        }

        /** A fetch when the app opens: no notification (the person is looking at the app). REPLACE, so the
         *  request returned is the one that runs and the caller's observer always gets its result. */
        fun fetchNow(ctx: Context): OneTimeWorkRequest = OneTimeWorkRequestBuilder<DailyWorker>()
            .setConstraints(network)
            .setInputData(workDataOf(KEY_NOTIFY to false))
            .build()
            .also { WorkManager.getInstance(ctx).enqueueUniqueWork(NOW, ExistingWorkPolicy.REPLACE, it) }
    }
}

object Paths {
    fun reports(ctx: Context) = java.io.File(ctx.filesDir, "reports")
}
