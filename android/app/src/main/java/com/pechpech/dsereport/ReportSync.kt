package com.pechpech.dsereport

import android.content.Context
import java.io.IOException

/** One download-and-save, shared by the daily alarm and the WorkManager jobs. Notifies only for a new session. */
object ReportSync {
    enum class Result { NEW, UPDATED, SAME, OFFLINE, INVALID }

    fun run(ctx: Context, notify: Boolean): Result {
        val store = ReportStore(Paths.reports(ctx))
        val body = try {
            ReportFetcher.fetch()
        } catch (e: IOException) {
            store.markOffline("Could not reach the report (${e.javaClass.simpleName})")
            return Result.OFFLINE
        }
        val (outcome, checked) = store.save(body)
        return when (outcome) {
            ReportStore.Outcome.NEW -> {
                if (notify && checked != null) Notifier.post(ctx, checked)
                Result.NEW
            }
            ReportStore.Outcome.UPDATED -> Result.UPDATED
            ReportStore.Outcome.SAME -> Result.SAME
            ReportStore.Outcome.INVALID -> Result.INVALID
        }
    }

    fun latestAsOf(ctx: Context): String? = ReportStore(Paths.reports(ctx)).latestAsOf
}
