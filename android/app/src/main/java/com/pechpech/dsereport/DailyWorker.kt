package com.pechpech.dsereport

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.time.DayOfWeek
import java.time.Duration
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.concurrent.TimeUnit

/**
 * Downloads the report, saves it, and notifies once per new session. On a trading day the report is published
 * from 16:50 Dhaka; until [LAST_TRY_HOUR] an unchanged report means "not out yet", so the job retries with back-off.
 */
class DailyWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val store = ReportStore(Paths.reports(applicationContext))
        val body = try {
            ReportFetcher.fetch()
        } catch (e: IOException) {
            store.markOffline("Could not reach the report (${e.javaClass.simpleName})")
            return@withContext if (runAttemptCount < MAX_ATTEMPTS) Result.retry() else Result.failure()
        }
        val (outcome, checked) = store.save(body)
        val notify = inputData.getBoolean(KEY_NOTIFY, true)
        when (outcome) {
            ReportStore.Outcome.NEW -> {
                if (notify && checked != null) Notifier.post(applicationContext, checked)
                Result.success(workDataOf(KEY_NEW to true))
            }
            ReportStore.Outcome.SAME ->
                if (notify && awaitingToday() && runAttemptCount < MAX_ATTEMPTS) Result.retry()
                else Result.success(workDataOf(KEY_NEW to false))
            ReportStore.Outcome.INVALID -> Result.failure()
        }
    }

    companion object {
        const val KEY_NOTIFY = "notify"
        const val KEY_NEW = "new"
        private const val DAILY = "daily-report"
        const val NOW = "report-now"
        private const val MAX_ATTEMPTS = 8
        private const val LAST_TRY_HOUR = 21
        private val DHAKA: ZoneId = ZoneId.of("Asia/Dhaka")
        private val TRADING = setOf(DayOfWeek.SUNDAY, DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY,
            DayOfWeek.THURSDAY)

        /** Trading day, after the close and before the last try: today's report may still be on its way. */
        fun awaitingToday(now: ZonedDateTime = ZonedDateTime.now(DHAKA)): Boolean =
            now.dayOfWeek in TRADING && now.hour in 16 until LAST_TRY_HOUR

        /** Delay to the next 17:05 Dhaka (the report is usually out by then). */
        fun delayToNextRun(now: ZonedDateTime = ZonedDateTime.now(DHAKA)): Duration {
            var next = now.withHour(17).withMinute(5).withSecond(0).withNano(0)
            if (!next.isAfter(now)) next = next.plusDays(1)
            return Duration.between(now, next)
        }

        private val network = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        fun schedule(ctx: Context) {
            val req = PeriodicWorkRequestBuilder<DailyWorker>(24, TimeUnit.HOURS)
                .setInitialDelay(delayToNextRun().toMinutes(), TimeUnit.MINUTES)
                .setConstraints(network)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 15, TimeUnit.MINUTES)
                .build()
            WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(DAILY, ExistingPeriodicWorkPolicy.UPDATE, req)
        }

        /** A fetch when the app opens: no notification (the person is looking at the app). */
        fun fetchNow(ctx: Context) = OneTimeWorkRequestBuilder<DailyWorker>()
            .setConstraints(network)
            .setInputData(workDataOf(KEY_NOTIFY to false))
            .build()
            .also { WorkManager.getInstance(ctx).enqueueUniqueWork(NOW, ExistingWorkPolicy.KEEP, it) }
    }
}

object Paths {
    fun reports(ctx: Context) = java.io.File(ctx.filesDir, "reports")
}
