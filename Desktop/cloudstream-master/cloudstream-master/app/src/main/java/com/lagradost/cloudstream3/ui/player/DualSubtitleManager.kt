package com.lagradost.cloudstream3.ui.player

import android.text.SpannableStringBuilder
import android.text.style.RelativeSizeSpan
import androidx.media3.common.text.Cue
import com.lagradost.cloudstream3.ui.player.SubtitleData

data class DualSubtitleCue(
    val startMs: Long,
    val endMs: Long,
    val text: CharSequence
)

object DualSubtitleManager {
    var secondarySub: SubtitleData? = null
    var secondaryCues: List<DualSubtitleCue> = emptyList()
    var secondaryDelayMs: Long = 0L
    var secondaryTextSizeRatio: Float = 0.85f
    var subtitleVerticalSpacingRatio: Float = 0.6f

    fun clearSecondary() {
        secondarySub = null
        secondaryCues = emptyList()
    }

    fun loadSecondaryFromText(content: String, sub: SubtitleData) {
        secondarySub = sub
        secondaryCues = parseSubtitleText(content)
    }

    fun parseSubtitleText(content: String): List<DualSubtitleCue> {
        val cues = mutableListOf<DualSubtitleCue>()
        try {
            val blocks = content.split(Regex("\\r?\\n\\s*\\r?\\n"))

            for (block in blocks) {
                val lines = block.trim().lines()
                if (lines.size < 2) continue

                var timeLineIndex = -1
                for (i in lines.indices) {
                    if (lines[i].contains("-->")) {
                        timeLineIndex = i
                        break
                    }
                }
                if (timeLineIndex == -1) continue

                val timeParts = lines[timeLineIndex].split("-->")
                if (timeParts.size < 2) continue

                val startMs = parseTimestamp(timeParts[0].trim())
                val endMs = parseTimestamp(timeParts[1].trim())
                if (startMs < 0 || endMs < 0 || endMs <= startMs) continue

                val textLines = lines.subList(timeLineIndex + 1, lines.size)
                val text = textanned(textLines.joinToString("\n"))

                cues.add(DualSubtitleCue(startMs, endMs, text))
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
        return cues
    }

    private fun parseTimestamp(timeStr: String): Long {
        try {
            val cleanTime = timeStr.split(" ").first().replace(',', '.')
            val parts = cleanTime.split(":")
            if (parts.size == 3) {
                val hours = parts[0].toLong()
                val minutes = parts[1].toLong()
                val secParts = parts[2].split(".")
                val seconds = secParts[0].toLong()
                val millis = if (secParts.size > 1) secParts[1].padEnd(3, '0').take(3).toLong() else 0L
                return hours * 3600000 + minutes * 60000 + seconds * 1000 + millis
            } else if (parts.size == 2) {
                val minutes = parts[0].toLong()
                val secParts = parts[1].split(".")
                val seconds = secParts[0].toLong()
                val millis = if (secParts.size > 1) secParts[1].padEnd(3, '0').take(3).toLong() else 0L
                return minutes * 60000 + seconds * 1000 + millis
            }
        } catch (e: Exception) {
            // ignore
        }
        return -1L
    }

    private fun textanned(raw: String): CharSequence {
        // Strip basic HTML tags if any (like <i>, <b>, <font>)
        return raw.replace(Regex("<[^>]*>"), "")
    }

    fun getCurrentSecondaryText(currentPosMs: Long): CharSequence? {
        if (secondaryCues.isEmpty()) return null
        val targetTime = currentPosMs - secondaryDelayMs
        val matchingCue = secondaryCues.find { targetTime in it.startMs..it.endMs }
        return matchingCue?.text
    }

    fun buildMergedCues(primaryCues: List<Cue>, secondaryText: CharSequence?): List<Cue> {
        val primaryText = primaryCues.firstOrNull()?.text?.toString()?.trim() ?: ""
        val cleanSec = secondaryText?.toString()?.trim() ?: ""

        val hasPrimary = primaryCues.isNotEmpty() && primaryText.isNotEmpty()
        val hasSecondary = cleanSec.isNotEmpty()

        if (!hasPrimary && !hasSecondary) return primaryCues

        // Prevent duplicate language rendering if Sub1 and Sub2 have identical text
        if (hasPrimary && hasSecondary && cleanSec.equals(primaryText, ignoreCase = true)) {
            return primaryCues
        }

        val builder = SpannableStringBuilder()

        if (hasSecondary) {
            builder.append(cleanSec)
            if (hasPrimary) {
                val spacingSpan = SpannableString("\n").apply {
                    setSpan(
                        RelativeSizeSpan(subtitleVerticalSpacingRatio),
                        0,
                        1,
                        Spanned.SPAN_EXCLUSIVE_EXCLUSIVE
                    )
                }
                builder.append(spacingSpan)
            }
        }

        if (hasPrimary) {
            builder.append(primaryText)
        }

        val baseCue = if (hasPrimary) primaryCues.first() else Cue.Builder().setText("").build()
        val merged = baseCue.buildUpon()
            .setText(builder)
            .build()

        return listOf(merged)
    }
}
