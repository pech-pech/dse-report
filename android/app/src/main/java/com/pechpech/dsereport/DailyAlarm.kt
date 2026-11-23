package com.pechpech.dsereport

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

/**
 * Wakes the app at [DailyWorker.RUN_TIMES] to download the report. An exact alarm when allowed (USE_EXACT_ALARM:
 * granted at install for this side-loaded app), else an inexact one that still fires in Doze. The alarm only
 * lasts until it fires or the phone restarts, so it is armed again after each run, at boot, after a clock or
 * time-zone change and after an update.
 */
object DailyAlarm {
    private const val REQUEST = 7

    private fun intent(ctx: Context) = PendingIntent.getBroadcast(
        ctx, REQUEST, Intent(ctx, AlarmReceiver::class.java).setAction(ACTION),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)

    const val ACTION = "com.pechpech.dsereport.DAILY"

    fun arm(ctx: Context) {
        val am = ctx.getSystemService(AlarmManager::class.java) ?: return
        val at = DailyWorker.nextRun().toInstant().toEpochMilli()
        val exact = Build.VERSION.SDK_INT < Build.VERSION_CODES.S || am.canScheduleExactAlarms()
        if (exact) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, intent(ctx))
        else am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, intent(ctx))
    }
}

/** The alarm itself, and boot / clock change / update, which clear or move alarms. */
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val app = ctx.applicationContext
        if (intent.action != DailyAlarm.ACTION) {
            DailyWorker.schedule(app)
            return
        }
        DailyAlarm.arm(app)                      // the next run first, whatever happens to this one
        val pending = goAsync()                  // the fetch is ~15 KB; the alarm's wake window allows network
        Thread {
            try {
                when (ReportSync.run(app, notify = true)) {
                    ReportSync.Result.NEW, ReportSync.Result.UPDATED, ReportSync.Result.INVALID -> Unit
                    ReportSync.Result.SAME, ReportSync.Result.OFFLINE ->
                        if (DailyWorker.awaitingToday(latest = ReportSync.latestAsOf(app))) DailyWorker.retrySoon(app)
                }
            } catch (e: Exception) {
                DailyWorker.retrySoon(app)
            } finally {
                pending.finish()
            }
        }.start()
    }
}
