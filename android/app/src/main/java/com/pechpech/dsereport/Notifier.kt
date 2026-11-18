package com.pechpech.dsereport

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

/** One notification per new session: title "DSEX +0.61% · 23 buys · 4 sells" and the summary lines. */
object Notifier {
    private const val CHANNEL = "daily-report"
    private const val ID = 1
    const val EXTRA_CARD = "card"
    const val SETUPS_CARD = 6

    fun ensureChannel(ctx: Context) {
        val ch = NotificationChannel(CHANNEL, ctx.getString(R.string.channel_name), NotificationManager.IMPORTANCE_DEFAULT)
        ch.description = ctx.getString(R.string.channel_desc)
        ctx.getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
    }

    private fun open(ctx: Context, card: Int, request: Int): PendingIntent {
        val i = Intent(ctx, MainActivity::class.java)
            .putExtra(EXTRA_CARD, card)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        return PendingIntent.getActivity(ctx, request, i, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    @android.annotation.SuppressLint("MissingPermission")   // checked on the first line
    fun post(ctx: Context, report: ReportStore.Checked) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        ensureChannel(ctx)
        val inbox = NotificationCompat.InboxStyle().setBigContentTitle(report.title)
        report.lines.forEach { inbox.addLine(it) }
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_report)
            .setColor(ContextCompat.getColor(ctx, R.color.up))
            .setContentTitle(report.title)
            .setContentText(report.lines.firstOrNull() ?: "Report for ${report.asOf}")
            .setStyle(inbox)
            .setContentIntent(open(ctx, 1, 1))
            .addAction(0, ctx.getString(R.string.action_setups), open(ctx, SETUPS_CARD, 2))
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(ctx).notify(ID, n)
    }
}
