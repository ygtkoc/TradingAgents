-- =============================================================================
-- Migration 0038 - Seed chart pattern knowledge corpus part 1
-- =============================================================================

BEGIN;

WITH payload AS (
  SELECT * FROM jsonb_to_recordset($json$
[
  {
    "title": "Bull Flag Continuation",
    "source_type": "strategy",
    "content_text": "Bull Flag Continuation is a chart-pattern setup that appears after a strong bullish impulse and a controlled downward or sideways flag consolidation. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when a candle closes above flag resistance with volume expansion or a clean retest hold. Invalidation occurs when price closes below the flag low or loses the impulse origin. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering inside the flag before breakout confirmation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "bull_flag",
        "continuation",
        "breakout",
        "trend"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "A candle closes above flag resistance with volume expansion or a clean retest hold.",
      "invalidation_logic": "Price closes below the flag low or loses the impulse origin.",
      "common_mistake": "Entering inside the flag before breakout confirmation."
    }
  },
  {
    "title": "Bear Flag Continuation",
    "source_type": "strategy",
    "content_text": "Bear Flag Continuation is a chart-pattern setup that appears after a strong bearish impulse and a controlled upward or sideways flag consolidation. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when a candle closes below flag support with sell volume or a failed retest. Invalidation occurs when price closes above the flag high or reclaims the breakdown level. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting the bounce before breakdown confirmation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "bear_flag",
        "continuation",
        "breakdown",
        "trend"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "A candle closes below flag support with sell volume or a failed retest.",
      "invalidation_logic": "Price closes above the flag high or reclaims the breakdown level.",
      "common_mistake": "Shorting the bounce before breakdown confirmation."
    }
  },
  {
    "title": "Bull Pennant Continuation",
    "source_type": "strategy",
    "content_text": "Bull Pennant Continuation is a chart-pattern setup that appears after an impulsive rally followed by tight triangular compression. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks above pennant resistance after volatility contraction. Invalidation occurs when price closes below pennant low or fails back into compression. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: calling a normal range a pennant without a prior impulse.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "bull_pennant",
        "continuation",
        "compression",
        "breakout"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks above pennant resistance after volatility contraction.",
      "invalidation_logic": "Price closes below pennant low or fails back into compression.",
      "common_mistake": "Calling a normal range a pennant without a prior impulse."
    }
  },
  {
    "title": "Bear Pennant Continuation",
    "source_type": "strategy",
    "content_text": "Bear Pennant Continuation is a chart-pattern setup that appears after an impulsive selloff followed by tight triangular compression. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks below pennant support with expanding bearish participation. Invalidation occurs when price closes above pennant high or breaks upward from compression. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering after the measured move is already mostly complete.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "bear_pennant",
        "continuation",
        "compression",
        "breakdown"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks below pennant support with expanding bearish participation.",
      "invalidation_logic": "Price closes above pennant high or breaks upward from compression.",
      "common_mistake": "Entering after the measured move is already mostly complete."
    }
  },
  {
    "title": "Ascending Triangle Breakout",
    "source_type": "strategy",
    "content_text": "Ascending Triangle Breakout is a chart-pattern setup that appears when higher lows press into a horizontal resistance zone. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes above horizontal resistance and preferably retests it as support. Invalidation occurs when price closes below the rising support line or last higher low. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying directly into resistance before breakout.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "ascending_triangle",
        "breakout",
        "resistance",
        "compression"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes above horizontal resistance and preferably retests it as support.",
      "invalidation_logic": "Price closes below the rising support line or last higher low.",
      "common_mistake": "Buying directly into resistance before breakout."
    }
  },
  {
    "title": "Descending Triangle Breakdown",
    "source_type": "strategy",
    "content_text": "Descending Triangle Breakdown is a chart-pattern setup that appears when lower highs press into a horizontal support zone. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes below support and retests it from below as resistance. Invalidation occurs when price reclaims support or closes above the last lower high. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting support too early while buyers still defend it.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "descending_triangle",
        "breakdown",
        "support",
        "compression"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes below support and retests it from below as resistance.",
      "invalidation_logic": "Price reclaims support or closes above the last lower high.",
      "common_mistake": "Shorting support too early while buyers still defend it."
    }
  },
  {
    "title": "Symmetrical Triangle Breakout",
    "source_type": "strategy",
    "content_text": "Symmetrical Triangle Breakout is a chart-pattern setup that appears when lower highs and higher lows compress price into a converging range. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes outside either boundary with volume or successful retest. Invalidation occurs when price closes back inside the triangle after breakout. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: predicting direction before price exits the triangle.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "symmetrical_triangle",
        "bilateral",
        "compression",
        "breakout"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes outside either boundary with volume or successful retest.",
      "invalidation_logic": "Price closes back inside the triangle after breakout.",
      "common_mistake": "Predicting direction before price exits the triangle."
    }
  },
  {
    "title": "Rising Wedge Breakdown",
    "source_type": "strategy",
    "content_text": "Rising Wedge Breakdown is a chart-pattern setup that appears when price rises inside narrowing upward-sloping boundaries after an extended advance. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes below wedge support and fails a retest. Invalidation occurs when price closes above wedge resistance with continuation strength. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting before the wedge support actually breaks.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "rising_wedge",
        "reversal",
        "bearish",
        "exhaustion"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes below wedge support and fails a retest.",
      "invalidation_logic": "Price closes above wedge resistance with continuation strength.",
      "common_mistake": "Shorting before the wedge support actually breaks."
    }
  },
  {
    "title": "Falling Wedge Breakout",
    "source_type": "strategy",
    "content_text": "Falling Wedge Breakout is a chart-pattern setup that appears when price falls inside narrowing downward-sloping boundaries after an extended decline. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes above wedge resistance and holds a retest. Invalidation occurs when price closes below wedge low or breakout fails back inside. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying every falling wedge without checking trend and liquidity context.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "falling_wedge",
        "reversal",
        "bullish",
        "exhaustion"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes above wedge resistance and holds a retest.",
      "invalidation_logic": "Price closes below wedge low or breakout fails back inside.",
      "common_mistake": "Buying every falling wedge without checking trend and liquidity context."
    }
  },
  {
    "title": "Double Top Neckline Breakdown",
    "source_type": "strategy",
    "content_text": "Double Top Neckline Breakdown is a chart-pattern setup that appears when price rejects the same resistance twice and fails to create a higher high. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes below the neckline and fails retest from below. Invalidation occurs when price reclaims neckline or breaks above the double-top resistance. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting the second top before neckline confirmation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "double_top",
        "reversal",
        "neckline",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes below the neckline and fails retest from below.",
      "invalidation_logic": "Price reclaims neckline or breaks above the double-top resistance.",
      "common_mistake": "Shorting the second top before neckline confirmation."
    }
  },
  {
    "title": "Double Bottom Neckline Breakout",
    "source_type": "strategy",
    "content_text": "Double Bottom Neckline Breakout is a chart-pattern setup that appears when price rejects the same support twice and fails to create a lower low. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes above neckline and holds retest as support. Invalidation occurs when price loses the second bottom or fails below neckline. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering before neckline breakout while market is still ranging.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "double_bottom",
        "reversal",
        "neckline",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes above neckline and holds retest as support.",
      "invalidation_logic": "Price loses the second bottom or fails below neckline.",
      "common_mistake": "Entering before neckline breakout while market is still ranging."
    }
  },
  {
    "title": "Triple Top Breakdown",
    "source_type": "strategy",
    "content_text": "Triple Top Breakdown is a chart-pattern setup that appears when three failed attempts occur at the same resistance zone. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when range support or neckline breaks with bearish continuation. Invalidation occurs when price closes above the triple-top resistance with acceptance. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: assuming the third resistance touch must reject even though repeated tests can weaken resistance.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "triple_top",
        "reversal",
        "resistance",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Range support or neckline breaks with bearish continuation.",
      "invalidation_logic": "Price closes above the triple-top resistance with acceptance.",
      "common_mistake": "Assuming the third resistance touch must reject even though repeated tests can weaken resistance."
    }
  },
  {
    "title": "Triple Bottom Breakout",
    "source_type": "strategy",
    "content_text": "Triple Bottom Breakout is a chart-pattern setup that appears when three failed attempts occur at the same support zone. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when range resistance or neckline breaks with bullish continuation. Invalidation occurs when price closes below the triple-bottom support with acceptance. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying support repeatedly without breakout from accumulation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "triple_bottom",
        "reversal",
        "support",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Range resistance or neckline breaks with bullish continuation.",
      "invalidation_logic": "Price closes below the triple-bottom support with acceptance.",
      "common_mistake": "Buying support repeatedly without breakout from accumulation."
    }
  },
  {
    "title": "Head And Shoulders Breakdown",
    "source_type": "strategy",
    "content_text": "Head And Shoulders Breakdown is a chart-pattern setup that appears after a left shoulder, higher head, and weaker right shoulder form near trend exhaustion. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when neckline breaks and retest fails from below. Invalidation occurs when price reclaims neckline or breaks above right shoulder. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: forcing the pattern on unclear swing structure.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "head_and_shoulders",
        "reversal",
        "neckline",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Neckline breaks and retest fails from below.",
      "invalidation_logic": "Price reclaims neckline or breaks above right shoulder.",
      "common_mistake": "Forcing the pattern on unclear swing structure."
    }
  },
  {
    "title": "Inverse Head And Shoulders Breakout",
    "source_type": "strategy",
    "content_text": "Inverse Head And Shoulders Breakout is a chart-pattern setup that appears after a left shoulder, lower head, and stronger right shoulder form near a bottom. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when neckline breaks and retest holds as support. Invalidation occurs when price loses right-shoulder low or fails back below neckline. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering before neckline breakout while downtrend remains intact.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "inverse_head_and_shoulders",
        "reversal",
        "neckline",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Neckline breaks and retest holds as support.",
      "invalidation_logic": "Price loses right-shoulder low or fails back below neckline.",
      "common_mistake": "Entering before neckline breakout while downtrend remains intact."
    }
  },
  {
    "title": "Cup And Handle Breakout",
    "source_type": "strategy",
    "content_text": "Cup And Handle Breakout is a chart-pattern setup that appears after a rounded base forms and a shallow handle pulls back near the rim. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes above the cup rim with volume and handle support holds. Invalidation occurs when price breaks below handle low or returns deeply into the cup. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying before the handle finishes forming.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "cup_and_handle",
        "base",
        "breakout",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes above the cup rim with volume and handle support holds.",
      "invalidation_logic": "Price breaks below handle low or returns deeply into the cup.",
      "common_mistake": "Buying before the handle finishes forming."
    }
  },
  {
    "title": "Inverted Cup And Handle Breakdown",
    "source_type": "strategy",
    "content_text": "Inverted Cup And Handle Breakdown is a chart-pattern setup that appears after a rounded top forms and a weak handle retraces upward. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes below handle support or base with bearish expansion. Invalidation occurs when price breaks above handle high or reclaims breakdown level. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting the rounded top before support fails.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "inverted_cup_and_handle",
        "distribution",
        "breakdown",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes below handle support or base with bearish expansion.",
      "invalidation_logic": "Price breaks above handle high or reclaims breakdown level.",
      "common_mistake": "Shorting the rounded top before support fails."
    }
  },
  {
    "title": "Rectangle Range Breakout",
    "source_type": "strategy",
    "content_text": "Rectangle Range Breakout is a chart-pattern setup that appears when price rotates between clear horizontal support and resistance. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes outside the rectangle and accepts beyond the boundary. Invalidation occurs when price closes back inside the range after breakout. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying range highs or shorting range lows without breakout confirmation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "rectangle",
        "range",
        "breakout",
        "support_resistance"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes outside the rectangle and accepts beyond the boundary.",
      "invalidation_logic": "Price closes back inside the range after breakout.",
      "common_mistake": "Buying range highs or shorting range lows without breakout confirmation."
    }
  },
  {
    "title": "Rounded Bottom Accumulation",
    "source_type": "strategy",
    "content_text": "Rounded Bottom Accumulation is a chart-pattern setup that appears when selling pressure fades gradually and price forms a curved base. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks base resistance and forms higher highs or higher lows. Invalidation occurs when price closes below the base low. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering too early before demand proves itself.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "rounded_bottom",
        "accumulation",
        "bullish_reversal",
        "base"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks base resistance and forms higher highs or higher lows.",
      "invalidation_logic": "Price closes below the base low.",
      "common_mistake": "Entering too early before demand proves itself."
    }
  },
  {
    "title": "Rounded Top Distribution",
    "source_type": "strategy",
    "content_text": "Rounded Top Distribution is a chart-pattern setup that appears when buying pressure fades gradually and price forms a curved top. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks base support and forms lower highs or lower lows. Invalidation occurs when price reclaims distribution resistance or last lower high. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: assuming a top before support actually fails.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "rounded_top",
        "distribution",
        "bearish_reversal",
        "base"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks base support and forms lower highs or lower lows.",
      "invalidation_logic": "Price reclaims distribution resistance or last lower high.",
      "common_mistake": "Assuming a top before support actually fails."
    }
  },
  {
    "title": "Broadening Wedge Breakout",
    "source_type": "strategy",
    "content_text": "Broadening Wedge Breakout is a chart-pattern setup that appears when price makes higher highs and lower lows with expanding volatility. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes outside a wedge boundary with acceptance. Invalidation occurs when price returns inside the wedge after breakout. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: trading the middle where risk is unclear.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "broadening_wedge",
        "volatility_expansion",
        "bilateral",
        "breakout"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes outside a wedge boundary with acceptance.",
      "invalidation_logic": "Price returns inside the wedge after breakout.",
      "common_mistake": "Trading the middle where risk is unclear."
    }
  },
  {
    "title": "Ascending Channel Breakdown",
    "source_type": "strategy",
    "content_text": "Ascending Channel Breakdown is a chart-pattern setup that appears when an orderly uptrend respects parallel rising support and resistance. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes below channel support and fails retest. Invalidation occurs when price reclaims broken channel support. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting too early while channel trend remains valid.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "ascending_channel",
        "channel",
        "breakdown",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes below channel support and fails retest.",
      "invalidation_logic": "Price reclaims broken channel support.",
      "common_mistake": "Shorting too early while channel trend remains valid."
    }
  },
  {
    "title": "Descending Channel Breakout",
    "source_type": "strategy",
    "content_text": "Descending Channel Breakout is a chart-pattern setup that appears when an orderly downtrend respects parallel falling support and resistance. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes above channel resistance and holds retest. Invalidation occurs when price closes back inside the descending channel. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying inside the channel before breakout.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "descending_channel",
        "channel",
        "breakout",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes above channel resistance and holds retest.",
      "invalidation_logic": "Price closes back inside the descending channel.",
      "common_mistake": "Buying inside the channel before breakout."
    }
  },
  {
    "title": "Horizontal Channel Breakout",
    "source_type": "strategy",
    "content_text": "Horizontal Channel Breakout is a chart-pattern setup that appears when price moves sideways between parallel horizontal boundaries. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes outside the channel and accepts beyond the range. Invalidation occurs when price closes back inside the channel. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: assuming every boundary touch is a reversal.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "horizontal_channel",
        "range",
        "breakout",
        "acceptance"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes outside the channel and accepts beyond the range.",
      "invalidation_logic": "Price closes back inside the channel.",
      "common_mistake": "Assuming every boundary touch is a reversal."
    }
  },
  {
    "title": "Breakout Retest Continuation",
    "source_type": "strategy",
    "content_text": "Breakout Retest Continuation is a chart-pattern setup that appears after price breaks a key level and returns to test it from the opposite side. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when the retested level rejects price in the breakout direction. Invalidation occurs when price closes back through the broken level. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering immediately on breakout without acceptance or retest.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "breakout_retest",
        "continuation",
        "support_resistance",
        "confirmation"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "The retested level rejects price in the breakout direction.",
      "invalidation_logic": "Price closes back through the broken level.",
      "common_mistake": "Entering immediately on breakout without acceptance or retest."
    }
  },
  {
    "title": "Failed Breakout Trap",
    "source_type": "strategy",
    "content_text": "Failed Breakout Trap is a chart-pattern setup that appears when price breaks a key level but quickly returns inside the prior range. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes back inside the range and rejects the false-break extreme. Invalidation occurs when price reclaims and accepts beyond the breakout level. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: holding a breakout trade after price returns inside the range.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "failed_breakout",
        "trap",
        "liquidity",
        "reversal"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes back inside the range and rejects the false-break extreme.",
      "invalidation_logic": "Price reclaims and accepts beyond the breakout level.",
      "common_mistake": "Holding a breakout trade after price returns inside the range."
    }
  },
  {
    "title": "Support Resistance Flip",
    "source_type": "strategy",
    "content_text": "Support Resistance Flip is a chart-pattern setup that appears when broken resistance becomes support or broken support becomes resistance. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price retests the flipped level and rejects in the new direction. Invalidation occurs when price closes back through the flipped level and holds there. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: treating every old level as valid without actual reaction.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "sr_flip",
        "retest",
        "support_resistance",
        "level_reaction"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price retests the flipped level and rejects in the new direction.",
      "invalidation_logic": "Price closes back through the flipped level and holds there.",
      "common_mistake": "Treating every old level as valid without actual reaction."
    }
  },
  {
    "title": "Measured Move Breakout",
    "source_type": "strategy",
    "content_text": "Measured Move Breakout is a chart-pattern setup that appears after a range, flag, or triangle breaks and projects a target based on pattern height. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when breakout accepts beyond structure and projected path has room before major liquidity. Invalidation occurs when breakout fails back inside the pattern. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: expecting the full measured move without partial profit or resistance checks.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "measured_move",
        "breakout",
        "targeting",
        "continuation"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Breakout accepts beyond structure and projected path has room before major liquidity.",
      "invalidation_logic": "Breakout fails back inside the pattern.",
      "common_mistake": "Expecting the full measured move without partial profit or resistance checks."
    }
  },
  {
    "title": "Continuation Gap And Go",
    "source_type": "strategy",
    "content_text": "Continuation Gap And Go is a chart-pattern setup that appears when price gaps or rapidly displaces above resistance and holds the gap/base. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price holds above the gap base and forms continuation structure. Invalidation occurs when price fills the gap and closes below breakout base. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: chasing the first expansion candle without retest.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "gap",
        "continuation",
        "momentum",
        "breakout"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price holds above the gap base and forms continuation structure.",
      "invalidation_logic": "Price fills the gap and closes below breakout base.",
      "common_mistake": "Chasing the first expansion candle without retest."
    }
  },
  {
    "title": "Exhaustion Gap Reversal",
    "source_type": "strategy",
    "content_text": "Exhaustion Gap Reversal is a chart-pattern setup that appears after a mature trend makes a final aggressive gap or displacement into liquidity. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects the gap extreme and breaks short-term structure against trend. Invalidation occurs when price accepts beyond the exhaustion extreme. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: fading strong continuation before reversal is confirmed.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "gap",
        "exhaustion",
        "reversal",
        "climax"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects the gap extreme and breaks short-term structure against trend.",
      "invalidation_logic": "Price accepts beyond the exhaustion extreme.",
      "common_mistake": "Fading strong continuation before reversal is confirmed."
    }
  },
  {
    "title": "Island Reversal",
    "source_type": "strategy",
    "content_text": "Island Reversal is a chart-pattern setup that appears when price isolates a cluster with a gap into it and a gap out against the prior direction. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when the second gap confirms rejection and price fails to refill immediately. Invalidation occurs when price closes back into the island range. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: using it on markets or charts where gaps are unreliable.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "island_reversal",
        "gap",
        "reversal",
        "exhaustion"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "The second gap confirms rejection and price fails to refill immediately.",
      "invalidation_logic": "Price closes back into the island range.",
      "common_mistake": "Using it on markets or charts where gaps are unreliable."
    }
  },
  {
    "title": "Diamond Top Reversal",
    "source_type": "strategy",
    "content_text": "Diamond Top Reversal is a chart-pattern setup that appears when price expands and then contracts near a market top, creating a diamond-like structure. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks the lower boundary with bearish acceptance. Invalidation occurs when price breaks above the diamond high. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting inside the diamond before breakdown.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "diamond_top",
        "reversal",
        "distribution",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks the lower boundary with bearish acceptance.",
      "invalidation_logic": "Price breaks above the diamond high.",
      "common_mistake": "Shorting inside the diamond before breakdown."
    }
  },
  {
    "title": "Diamond Bottom Reversal",
    "source_type": "strategy",
    "content_text": "Diamond Bottom Reversal is a chart-pattern setup that appears when price expands and then contracts near a bottom, creating a diamond-like structure. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks the upper boundary with bullish acceptance. Invalidation occurs when price breaks below the diamond low. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying inside the diamond before breakout.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "diamond_bottom",
        "reversal",
        "accumulation",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks the upper boundary with bullish acceptance.",
      "invalidation_logic": "Price breaks below the diamond low.",
      "common_mistake": "Buying inside the diamond before breakout."
    }
  },
  {
    "title": "V Bottom Reversal",
    "source_type": "strategy",
    "content_text": "V Bottom Reversal is a chart-pattern setup that appears after a sharp capitulation move quickly reverses with aggressive demand. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price reclaims a key level and forms higher-low continuation. Invalidation occurs when price loses the capitulation low or reclaim level. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying the falling move before a reclaim appears.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "v_bottom",
        "reversal",
        "capitulation",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price reclaims a key level and forms higher-low continuation.",
      "invalidation_logic": "Price loses the capitulation low or reclaim level.",
      "common_mistake": "Buying the falling move before a reclaim appears."
    }
  },
  {
    "title": "V Top Reversal",
    "source_type": "strategy",
    "content_text": "V Top Reversal is a chart-pattern setup that appears after a sharp blowoff move quickly reverses with aggressive selling. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price loses a key level and forms lower-high continuation. Invalidation occurs when price reclaims the blowoff high or breakdown level. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting the vertical rise before sellers actually take control.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "v_top",
        "reversal",
        "blowoff",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price loses a key level and forms lower-high continuation.",
      "invalidation_logic": "Price reclaims the blowoff high or breakdown level.",
      "common_mistake": "Shorting the vertical rise before sellers actually take control."
    }
  },
  {
    "title": "Adam And Eve Bottom",
    "source_type": "strategy",
    "content_text": "Adam And Eve Bottom is a chart-pattern setup that appears when a sharp V-shaped low is followed by a rounded second low near the same support. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks neckline resistance after the second bottom stabilizes. Invalidation occurs when price closes below the second bottom or base support. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering during the rounded base before neckline confirmation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "adam_eve_bottom",
        "reversal",
        "bullish",
        "base"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks neckline resistance after the second bottom stabilizes.",
      "invalidation_logic": "Price closes below the second bottom or base support.",
      "common_mistake": "Entering during the rounded base before neckline confirmation."
    }
  },
  {
    "title": "Adam And Eve Top",
    "source_type": "strategy",
    "content_text": "Adam And Eve Top is a chart-pattern setup that appears when a sharp spike high is followed by a rounded second top near resistance. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks neckline support after the second top weakens. Invalidation occurs when price closes above the second top or resistance. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting the rounded top before support breaks.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "adam_eve_top",
        "reversal",
        "bearish",
        "distribution"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks neckline support after the second top weakens.",
      "invalidation_logic": "Price closes above the second top or resistance.",
      "common_mistake": "Shorting the rounded top before support breaks."
    }
  },
  {
    "title": "Eve And Adam Bottom",
    "source_type": "strategy",
    "content_text": "Eve And Adam Bottom is a chart-pattern setup that appears when a rounded first bottom is followed by a sharper V-shaped second low. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks neckline resistance after second-low rejection. Invalidation occurs when price closes below the second low. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: assuming the second sharp low is bullish before it reclaims support.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "eve_adam_bottom",
        "reversal",
        "bullish",
        "base"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks neckline resistance after second-low rejection.",
      "invalidation_logic": "Price closes below the second low.",
      "common_mistake": "Assuming the second sharp low is bullish before it reclaims support."
    }
  },
  {
    "title": "Eve And Adam Top",
    "source_type": "strategy",
    "content_text": "Eve And Adam Top is a chart-pattern setup that appears when a rounded first top is followed by a sharper spike high. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks neckline support after the spike rejects. Invalidation occurs when price closes above the spike high. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting the spike without confirmation below neckline.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "eve_adam_top",
        "reversal",
        "bearish",
        "distribution"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks neckline support after the spike rejects.",
      "invalidation_logic": "Price closes above the spike high.",
      "common_mistake": "Shorting the spike without confirmation below neckline."
    }
  },
  {
    "title": "Complex Head And Shoulders",
    "source_type": "strategy",
    "content_text": "Complex Head And Shoulders is a chart-pattern setup that appears when multiple shoulders or uneven peaks form around a broader topping structure. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when a clear neckline breaks with acceptance despite pattern complexity. Invalidation occurs when price reclaims neckline or invalidates the right-side structure. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: forcing symmetry instead of focusing on neckline and structure.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "complex_head_and_shoulders",
        "reversal",
        "bearish",
        "neckline"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "A clear neckline breaks with acceptance despite pattern complexity.",
      "invalidation_logic": "Price reclaims neckline or invalidates the right-side structure.",
      "common_mistake": "Forcing symmetry instead of focusing on neckline and structure."
    }
  },
  {
    "title": "Complex Inverse Head And Shoulders",
    "source_type": "strategy",
    "content_text": "Complex Inverse Head And Shoulders is a chart-pattern setup that appears when multiple shoulders or uneven lows form around a broader bottoming structure. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when a clear neckline breaks with bullish acceptance. Invalidation occurs when price loses neckline or right-side support. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: ignoring that complex bases require patience and confirmation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "complex_inverse_head_and_shoulders",
        "reversal",
        "bullish",
        "neckline"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "A clear neckline breaks with bullish acceptance.",
      "invalidation_logic": "Price loses neckline or right-side support.",
      "common_mistake": "Ignoring that complex bases require patience and confirmation."
    }
  },
  {
    "title": "Right Angled Ascending Broadening Formation",
    "source_type": "strategy",
    "content_text": "Right Angled Ascending Broadening Formation is a chart-pattern setup that appears when horizontal resistance is tested while lows expand downward and volatility increases. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks above horizontal resistance with acceptance. Invalidation occurs when price rejects resistance and loses the latest broadening low. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying every dip in an expanding volatile structure.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "ascending_broadening",
        "volatility",
        "breakout",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks above horizontal resistance with acceptance.",
      "invalidation_logic": "Price rejects resistance and loses the latest broadening low.",
      "common_mistake": "Buying every dip in an expanding volatile structure."
    }
  },
  {
    "title": "Right Angled Descending Broadening Formation",
    "source_type": "strategy",
    "content_text": "Right Angled Descending Broadening Formation is a chart-pattern setup that appears when horizontal support is tested while highs expand upward and volatility increases. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks below horizontal support with acceptance. Invalidation occurs when price reclaims support and breaks the latest broadening high. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting every rally before support breaks.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "descending_broadening",
        "volatility",
        "breakdown",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks below horizontal support with acceptance.",
      "invalidation_logic": "Price reclaims support and breaks the latest broadening high.",
      "common_mistake": "Shorting every rally before support breaks."
    }
  },
  {
    "title": "Megaphone Top",
    "source_type": "strategy",
    "content_text": "Megaphone Top is a chart-pattern setup that appears when larger swings expand near a top and market disagreement increases. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks the lower broadening boundary or fails after sweeping highs. Invalidation occurs when price accepts above the upper boundary. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: trading large swings without adjusting risk to volatility.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "megaphone_top",
        "broadening",
        "bearish",
        "distribution"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks the lower broadening boundary or fails after sweeping highs.",
      "invalidation_logic": "Price accepts above the upper boundary.",
      "common_mistake": "Trading large swings without adjusting risk to volatility."
    }
  },
  {
    "title": "Megaphone Bottom",
    "source_type": "strategy",
    "content_text": "Megaphone Bottom is a chart-pattern setup that appears when larger swings expand near a bottom and volatility washes out both sides. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks the upper broadening boundary or reclaims after sweeping lows. Invalidation occurs when price accepts below the lower boundary. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying before the market confirms accumulation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "megaphone_bottom",
        "broadening",
        "bullish",
        "accumulation"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks the upper broadening boundary or reclaims after sweeping lows.",
      "invalidation_logic": "Price accepts below the lower boundary.",
      "common_mistake": "Buying before the market confirms accumulation."
    }
  },
  {
    "title": "Bump And Run Reversal Top",
    "source_type": "strategy",
    "content_text": "Bump And Run Reversal Top is a chart-pattern setup that appears when an orderly uptrend accelerates into a steep unsustainable bump. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks the accelerated trendline and then the original trendline. Invalidation occurs when price reclaims the bump high or accelerated trendline. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting parabolic strength before trendline break.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "bump_and_run",
        "reversal",
        "bearish",
        "parabolic"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks the accelerated trendline and then the original trendline.",
      "invalidation_logic": "Price reclaims the bump high or accelerated trendline.",
      "common_mistake": "Shorting parabolic strength before trendline break."
    }
  },
  {
    "title": "Bump And Run Reversal Bottom",
    "source_type": "strategy",
    "content_text": "Bump And Run Reversal Bottom is a chart-pattern setup that appears when an orderly downtrend accelerates into a steep unsustainable selloff. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks the accelerated downtrend line and reclaims original structure. Invalidation occurs when price loses the capitulation low or fails reclaim. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying capitulation without a trendline or structure break.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "bump_and_run_bottom",
        "reversal",
        "bullish",
        "capitulation"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks the accelerated downtrend line and reclaims original structure.",
      "invalidation_logic": "Price loses the capitulation low or fails reclaim.",
      "common_mistake": "Buying capitulation without a trendline or structure break."
    }
  },
  {
    "title": "Parabolic Curve Breakdown",
    "source_type": "strategy",
    "content_text": "Parabolic Curve Breakdown is a chart-pattern setup that appears when price rises in increasingly steep arcs and late buyers chase vertically. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks the parabolic curve support and fails retest. Invalidation occurs when price reclaims the curve or makes new highs with acceptance. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting early while the parabolic phase is still expanding.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "parabolic_curve",
        "breakdown",
        "exhaustion",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks the parabolic curve support and fails retest.",
      "invalidation_logic": "Price reclaims the curve or makes new highs with acceptance.",
      "common_mistake": "Shorting early while the parabolic phase is still expanding."
    }
  },
  {
    "title": "Parabolic Selloff Reclaim",
    "source_type": "strategy",
    "content_text": "Parabolic Selloff Reclaim is a chart-pattern setup that appears when price falls in increasingly steep arcs and forced selling accelerates. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price reclaims the final acceleration level and forms higher lows. Invalidation occurs when price loses the capitulation low. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: catching the knife before reclaim and volatility stabilization.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "parabolic_selloff",
        "reclaim",
        "exhaustion",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price reclaims the final acceleration level and forms higher lows.",
      "invalidation_logic": "Price loses the capitulation low.",
      "common_mistake": "Catching the knife before reclaim and volatility stabilization."
    }
  },
  {
    "title": "Base Breakout",
    "source_type": "strategy",
    "content_text": "Base Breakout is a chart-pattern setup that appears after price forms a tight sideways base with decreasing volatility. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes above base resistance with volume and holds retest. Invalidation occurs when price closes back inside the base or below base support. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying random sideways chop without compression or volume context.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "base_breakout",
        "accumulation",
        "breakout",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes above base resistance with volume and holds retest.",
      "invalidation_logic": "Price closes back inside the base or below base support.",
      "common_mistake": "Buying random sideways chop without compression or volume context."
    }
  },
  {
    "title": "Base Breakdown",
    "source_type": "strategy",
    "content_text": "Base Breakdown is a chart-pattern setup that appears after price forms a tight sideways base that fails to advance. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes below base support with expanding sell pressure. Invalidation occurs when price reclaims the base support or closes back inside. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting a base before support actually fails.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "base_breakdown",
        "distribution",
        "breakdown",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes below base support with expanding sell pressure.",
      "invalidation_logic": "Price reclaims the base support or closes back inside.",
      "common_mistake": "Shorting a base before support actually fails."
    }
  },
  {
    "title": "High Tight Flag",
    "source_type": "strategy",
    "content_text": "High Tight Flag is a chart-pattern setup that appears after a very strong vertical advance followed by shallow, tight consolidation near highs. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks above the tight flag with volume and holds above midpoint. Invalidation occurs when price closes below the flag low or loses the prior momentum base. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying after the move is too extended without tight consolidation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "high_tight_flag",
        "momentum",
        "continuation",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks above the tight flag with volume and holds above midpoint.",
      "invalidation_logic": "Price closes below the flag low or loses the prior momentum base.",
      "common_mistake": "Buying after the move is too extended without tight consolidation."
    }
  },
  {
    "title": "Low Tight Flag",
    "source_type": "strategy",
    "content_text": "Low Tight Flag is a chart-pattern setup that appears after a very strong vertical decline followed by shallow, tight consolidation near lows. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks below the tight flag with sell volume. Invalidation occurs when price closes above the flag high or reclaims prior breakdown base. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting after exhaustion instead of after tight continuation structure.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "low_tight_flag",
        "momentum",
        "continuation",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks below the tight flag with sell volume.",
      "invalidation_logic": "Price closes above the flag high or reclaims prior breakdown base.",
      "common_mistake": "Shorting after exhaustion instead of after tight continuation structure."
    }
  },
  {
    "title": "Flat Base Breakout",
    "source_type": "strategy",
    "content_text": "Flat Base Breakout is a chart-pattern setup that appears when price holds a narrow horizontal base after an uptrend or accumulation phase. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes above flat resistance with volume and low pullback depth. Invalidation occurs when price closes below flat base support. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering while base is still incomplete.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "flat_base",
        "breakout",
        "accumulation",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes above flat resistance with volume and low pullback depth.",
      "invalidation_logic": "Price closes below flat base support.",
      "common_mistake": "Entering while base is still incomplete."
    }
  },
  {
    "title": "Saucer With Handle",
    "source_type": "strategy",
    "content_text": "Saucer With Handle is a chart-pattern setup that appears after a long rounded bottom followed by a smaller pullback handle. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks handle resistance and then the saucer rim. Invalidation occurs when price loses handle low or base support. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: treating any rounded shape as a saucer without handle confirmation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "saucer_handle",
        "rounded_bottom",
        "handle",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks handle resistance and then the saucer rim.",
      "invalidation_logic": "Price loses handle low or base support.",
      "common_mistake": "Treating any rounded shape as a saucer without handle confirmation."
    }
  },
  {
    "title": "Scallop Ascending Pattern",
    "source_type": "strategy",
    "content_text": "Scallop Ascending Pattern is a chart-pattern setup that appears when price makes a rounded pullback that recovers into a continuation breakout. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks above the scallop lip and holds retest. Invalidation occurs when price loses the rounded pullback low. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering before the recovery reaches the lip.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "scallop",
        "continuation",
        "bullish",
        "pullback"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks above the scallop lip and holds retest.",
      "invalidation_logic": "Price loses the rounded pullback low.",
      "common_mistake": "Entering before the recovery reaches the lip."
    }
  },
  {
    "title": "Inverted Scallop Pattern",
    "source_type": "strategy",
    "content_text": "Inverted Scallop Pattern is a chart-pattern setup that appears when price makes a rounded bounce that rolls over into a continuation breakdown. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks below the scallop base and fails retest. Invalidation occurs when price breaks above the rounded bounce high. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting before rollover confirms.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "inverted_scallop",
        "continuation",
        "bearish",
        "pullback"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks below the scallop base and fails retest.",
      "invalidation_logic": "Price breaks above the rounded bounce high.",
      "common_mistake": "Shorting before rollover confirms."
    }
  },
  {
    "title": "Pullback To Broken Trendline",
    "source_type": "strategy",
    "content_text": "Pullback To Broken Trendline is a chart-pattern setup that appears after price breaks a trendline and returns to retest it from the other side. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when the retest rejects and price continues away from the broken trendline. Invalidation occurs when price closes back through the trendline and invalidates the break. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: drawing trendlines through too many candles to force a setup.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "trendline_retest",
        "pullback",
        "continuation",
        "confirmation"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "The retest rejects and price continues away from the broken trendline.",
      "invalidation_logic": "Price closes back through the trendline and invalidates the break.",
      "common_mistake": "Drawing trendlines through too many candles to force a setup."
    }
  },
  {
    "title": "Trendline Break Reversal",
    "source_type": "strategy",
    "content_text": "Trendline Break Reversal is a chart-pattern setup that appears when a mature trendline that has guided price is decisively broken. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when break is followed by structure shift and failed retest. Invalidation occurs when price reclaims the trendline and resumes prior trend. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: treating a small wick through trendline as confirmed reversal.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "trendline_break",
        "reversal",
        "structure_shift",
        "price_action"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Break is followed by structure shift and failed retest.",
      "invalidation_logic": "Price reclaims the trendline and resumes prior trend.",
      "common_mistake": "Treating a small wick through trendline as confirmed reversal."
    }
  },
  {
    "title": "Three Drives Top",
    "source_type": "strategy",
    "content_text": "Three Drives Top is a chart-pattern setup that appears when price forms three successive pushes higher with weakening momentum. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when third drive rejects near projection or resistance and structure breaks down. Invalidation occurs when price accepts above the third drive high. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting the third push before rejection and structure break.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "three_drives",
        "reversal",
        "bearish",
        "harmonic"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Third drive rejects near projection or resistance and structure breaks down.",
      "invalidation_logic": "Price accepts above the third drive high.",
      "common_mistake": "Shorting the third push before rejection and structure break."
    }
  },
  {
    "title": "Three Drives Bottom",
    "source_type": "strategy",
    "content_text": "Three Drives Bottom is a chart-pattern setup that appears when price forms three successive pushes lower with weakening downside momentum. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when third drive rejects near projection or support and structure breaks upward. Invalidation occurs when price accepts below the third drive low. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying the third push before reclaim or reversal confirmation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "three_drives",
        "reversal",
        "bullish",
        "harmonic"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Third drive rejects near projection or support and structure breaks upward.",
      "invalidation_logic": "Price accepts below the third drive low.",
      "common_mistake": "Buying the third push before reclaim or reversal confirmation."
    }
  },
  {
    "title": "ABCD Bullish Completion",
    "source_type": "strategy",
    "content_text": "ABCD Bullish Completion is a chart-pattern setup that appears when a measured corrective move completes near Fibonacci or structural support. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects completion zone and breaks minor resistance. Invalidation occurs when price closes below the D point or support zone. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: placing blind orders at D without reversal confirmation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "abcd",
        "harmonic",
        "bullish",
        "retracement"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects completion zone and breaks minor resistance.",
      "invalidation_logic": "Price closes below the D point or support zone.",
      "common_mistake": "Placing blind orders at D without reversal confirmation."
    }
  },
  {
    "title": "ABCD Bearish Completion",
    "source_type": "strategy",
    "content_text": "ABCD Bearish Completion is a chart-pattern setup that appears when a measured corrective rally completes near Fibonacci or structural resistance. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects completion zone and breaks minor support. Invalidation occurs when price closes above the D point or resistance zone. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting the D point without rejection confirmation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "abcd",
        "harmonic",
        "bearish",
        "retracement"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects completion zone and breaks minor support.",
      "invalidation_logic": "Price closes above the D point or resistance zone.",
      "common_mistake": "Shorting the D point without rejection confirmation."
    }
  },
  {
    "title": "Gartley Bullish Pattern",
    "source_type": "strategy",
    "content_text": "Gartley Bullish Pattern is a chart-pattern setup that appears when XA, AB, BC, and CD legs complete near bullish harmonic Fibonacci confluence. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price reacts from PRZ and breaks short-term bearish structure. Invalidation occurs when price closes below the PRZ and X point context fails. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: using loose Fibonacci ratios to force a Gartley.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "gartley",
        "harmonic",
        "bullish",
        "fibonacci"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price reacts from PRZ and breaks short-term bearish structure.",
      "invalidation_logic": "Price closes below the PRZ and X point context fails.",
      "common_mistake": "Using loose Fibonacci ratios to force a Gartley."
    }
  },
  {
    "title": "Gartley Bearish Pattern",
    "source_type": "strategy",
    "content_text": "Gartley Bearish Pattern is a chart-pattern setup that appears when XA, AB, BC, and CD legs complete near bearish harmonic Fibonacci confluence. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects PRZ and breaks short-term bullish structure. Invalidation occurs when price closes above the PRZ and X point context fails. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting the PRZ before rejection appears.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "gartley",
        "harmonic",
        "bearish",
        "fibonacci"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects PRZ and breaks short-term bullish structure.",
      "invalidation_logic": "Price closes above the PRZ and X point context fails.",
      "common_mistake": "Shorting the PRZ before rejection appears."
    }
  },
  {
    "title": "Bat Bullish Pattern",
    "source_type": "strategy",
    "content_text": "Bat Bullish Pattern is a chart-pattern setup that appears when a deep harmonic retracement completes near the bullish bat potential reversal zone. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects PRZ and forms bullish structure shift. Invalidation occurs when price closes below the PRZ with acceptance. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: ignoring the required deep retracement ratios.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "bat_pattern",
        "harmonic",
        "bullish",
        "fibonacci"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects PRZ and forms bullish structure shift.",
      "invalidation_logic": "Price closes below the PRZ with acceptance.",
      "common_mistake": "Ignoring the required deep retracement ratios."
    }
  },
  {
    "title": "Bat Bearish Pattern",
    "source_type": "strategy",
    "content_text": "Bat Bearish Pattern is a chart-pattern setup that appears when a deep harmonic retracement completes near the bearish bat potential reversal zone. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects PRZ and forms bearish structure shift. Invalidation occurs when price closes above the PRZ with acceptance. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering before PRZ rejection confirms.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "bat_pattern",
        "harmonic",
        "bearish",
        "fibonacci"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects PRZ and forms bearish structure shift.",
      "invalidation_logic": "Price closes above the PRZ with acceptance.",
      "common_mistake": "Entering before PRZ rejection confirms."
    }
  },
  {
    "title": "Butterfly Bullish Pattern",
    "source_type": "strategy",
    "content_text": "Butterfly Bullish Pattern is a chart-pattern setup that appears when price extends beyond the original X point into a bullish reversal zone. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects the extension zone and reclaims minor resistance. Invalidation occurs when price continues below the PRZ with acceptance. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying only because extension target is reached.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "butterfly",
        "harmonic",
        "bullish",
        "extension"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects the extension zone and reclaims minor resistance.",
      "invalidation_logic": "Price continues below the PRZ with acceptance.",
      "common_mistake": "Buying only because extension target is reached."
    }
  },
  {
    "title": "Butterfly Bearish Pattern",
    "source_type": "strategy",
    "content_text": "Butterfly Bearish Pattern is a chart-pattern setup that appears when price extends beyond the original X point into a bearish reversal zone. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects the extension zone and loses minor support. Invalidation occurs when price continues above the PRZ with acceptance. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting a strong extension without reversal structure.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "butterfly",
        "harmonic",
        "bearish",
        "extension"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects the extension zone and loses minor support.",
      "invalidation_logic": "Price continues above the PRZ with acceptance.",
      "common_mistake": "Shorting a strong extension without reversal structure."
    }
  },
  {
    "title": "Crab Bullish Pattern",
    "source_type": "strategy",
    "content_text": "Crab Bullish Pattern is a chart-pattern setup that appears when a deep extension completes near an extreme bullish harmonic PRZ. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects the PRZ and breaks local bearish structure. Invalidation occurs when price closes below PRZ and volatility expands lower. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: using oversized stops because the pattern is extreme.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "crab",
        "harmonic",
        "bullish",
        "extension"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects the PRZ and breaks local bearish structure.",
      "invalidation_logic": "Price closes below PRZ and volatility expands lower.",
      "common_mistake": "Using oversized stops because the pattern is extreme."
    }
  },
  {
    "title": "Crab Bearish Pattern",
    "source_type": "strategy",
    "content_text": "Crab Bearish Pattern is a chart-pattern setup that appears when a deep extension completes near an extreme bearish harmonic PRZ. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects the PRZ and breaks local bullish structure. Invalidation occurs when price closes above PRZ and volatility expands higher. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting too early before the final extension completes.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "crab",
        "harmonic",
        "bearish",
        "extension"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects the PRZ and breaks local bullish structure.",
      "invalidation_logic": "Price closes above PRZ and volatility expands higher.",
      "common_mistake": "Shorting too early before the final extension completes."
    }
  },
  {
    "title": "Shark Bullish Pattern",
    "source_type": "strategy",
    "content_text": "Shark Bullish Pattern is a chart-pattern setup that appears when a volatile harmonic structure completes near a bullish reversal zone. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects the PRZ and breaks short-term resistance. Invalidation occurs when price accepts below the PRZ. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: mislabeling random volatility as a shark pattern.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "shark",
        "harmonic",
        "bullish",
        "reversal"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects the PRZ and breaks short-term resistance.",
      "invalidation_logic": "Price accepts below the PRZ.",
      "common_mistake": "Mislabeling random volatility as a shark pattern."
    }
  },
  {
    "title": "Shark Bearish Pattern",
    "source_type": "strategy",
    "content_text": "Shark Bearish Pattern is a chart-pattern setup that appears when a volatile harmonic structure completes near a bearish reversal zone. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price rejects the PRZ and breaks short-term support. Invalidation occurs when price accepts above the PRZ. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering without waiting for rejection from PRZ.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "shark",
        "harmonic",
        "bearish",
        "reversal"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price rejects the PRZ and breaks short-term support.",
      "invalidation_logic": "Price accepts above the PRZ.",
      "common_mistake": "Entering without waiting for rejection from PRZ."
    }
  },
  {
    "title": "Cypher Bullish Pattern",
    "source_type": "strategy",
    "content_text": "Cypher Bullish Pattern is a chart-pattern setup that appears when a specific XA-AB-BC-CD harmonic sequence completes near bullish PRZ. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price reacts from PRZ and confirms with bullish structure shift. Invalidation occurs when price closes below PRZ and fails to reclaim. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: forcing the pattern when B and C legs do not meet rules.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "cypher",
        "harmonic",
        "bullish",
        "fibonacci"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price reacts from PRZ and confirms with bullish structure shift.",
      "invalidation_logic": "Price closes below PRZ and fails to reclaim.",
      "common_mistake": "Forcing the pattern when B and C legs do not meet rules."
    }
  },
  {
    "title": "Cypher Bearish Pattern",
    "source_type": "strategy",
    "content_text": "Cypher Bearish Pattern is a chart-pattern setup that appears when a specific XA-AB-BC-CD harmonic sequence completes near bearish PRZ. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price reacts from PRZ and confirms with bearish structure shift. Invalidation occurs when price closes above PRZ and fails to reject. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting before the D leg completes.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "cypher",
        "harmonic",
        "bearish",
        "fibonacci"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price reacts from PRZ and confirms with bearish structure shift.",
      "invalidation_logic": "Price closes above PRZ and fails to reject.",
      "common_mistake": "Shorting before the D leg completes."
    }
  },
  {
    "title": "Rounding Handle Breakout",
    "source_type": "strategy",
    "content_text": "Rounding Handle Breakout is a chart-pattern setup that appears when a rounded recovery pauses in a shallow handle near resistance. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when handle resistance breaks and price accepts above the rounded structure. Invalidation occurs when price loses handle low or rounded base midpoint. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering during handle pullback without breakout.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "rounding_handle",
        "breakout",
        "bullish",
        "continuation"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Handle resistance breaks and price accepts above the rounded structure.",
      "invalidation_logic": "Price loses handle low or rounded base midpoint.",
      "common_mistake": "Entering during handle pullback without breakout."
    }
  },
  {
    "title": "Descending Stair Step Breakdown",
    "source_type": "strategy",
    "content_text": "Descending Stair Step Breakdown is a chart-pattern setup that appears when price forms repeated lower shelves and lower highs in a downtrend. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when each shelf breaks and retests from below. Invalidation occurs when price breaks above the most recent lower high. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting after several shelves when trend is already exhausted.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "stair_step",
        "downtrend",
        "continuation",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Each shelf breaks and retests from below.",
      "invalidation_logic": "Price breaks above the most recent lower high.",
      "common_mistake": "Shorting after several shelves when trend is already exhausted."
    }
  },
  {
    "title": "Ascending Stair Step Breakout",
    "source_type": "strategy",
    "content_text": "Ascending Stair Step Breakout is a chart-pattern setup that appears when price forms repeated higher shelves and higher lows in an uptrend. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when each shelf breaks upward and holds retest as support. Invalidation occurs when price breaks below the most recent higher low. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying after several steps without assessing extension.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "stair_step",
        "uptrend",
        "continuation",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Each shelf breaks upward and holds retest as support.",
      "invalidation_logic": "Price breaks below the most recent higher low.",
      "common_mistake": "Buying after several steps without assessing extension."
    }
  },
  {
    "title": "Compression Under Resistance",
    "source_type": "strategy",
    "content_text": "Compression Under Resistance is a chart-pattern setup that appears when price repeatedly presses into resistance with shallow pullbacks and rising lows. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when resistance breaks with acceptance and volume expansion. Invalidation occurs when price loses the compression lows. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting resistance only because it has been touched many times.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "compression",
        "resistance",
        "breakout",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Resistance breaks with acceptance and volume expansion.",
      "invalidation_logic": "Price loses the compression lows.",
      "common_mistake": "Shorting resistance only because it has been touched many times."
    }
  },
  {
    "title": "Compression Above Support",
    "source_type": "strategy",
    "content_text": "Compression Above Support is a chart-pattern setup that appears when price repeatedly presses into support with shallow bounces and falling highs. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when support breaks with acceptance and sell volume. Invalidation occurs when price reclaims the compression highs. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying support only because it has held several times.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "compression",
        "support",
        "breakdown",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Support breaks with acceptance and sell volume.",
      "invalidation_logic": "Price reclaims the compression highs.",
      "common_mistake": "Buying support only because it has held several times."
    }
  },
  {
    "title": "Liquidity Sweep Reversal Above Range",
    "source_type": "strategy",
    "content_text": "Liquidity Sweep Reversal Above Range is a chart-pattern setup that appears when price sweeps above range high then closes back inside. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when bearish structure shift occurs after reclaiming below range high. Invalidation occurs when price accepts above the range high. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting before the sweep returns inside the range.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "range_sweep",
        "liquidity",
        "bearish_reversal",
        "trap"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Bearish structure shift occurs after reclaiming below range high.",
      "invalidation_logic": "Price accepts above the range high.",
      "common_mistake": "Shorting before the sweep returns inside the range."
    }
  },
  {
    "title": "Liquidity Sweep Reversal Below Range",
    "source_type": "strategy",
    "content_text": "Liquidity Sweep Reversal Below Range is a chart-pattern setup that appears when price sweeps below range low then closes back inside. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when bullish structure shift occurs after reclaiming above range low. Invalidation occurs when price accepts below the range low. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying before the sweep returns inside the range.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "range_sweep",
        "liquidity",
        "bullish_reversal",
        "trap"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Bullish structure shift occurs after reclaiming above range low.",
      "invalidation_logic": "Price accepts below the range low.",
      "common_mistake": "Buying before the sweep returns inside the range."
    }
  },
  {
    "title": "Range Expansion Candle Breakout",
    "source_type": "strategy",
    "content_text": "Range Expansion Candle Breakout is a chart-pattern setup that appears when a candle expands beyond recent average range and breaks structure. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when expansion candle closes outside the range and follow-through holds. Invalidation occurs when price retraces more than half and closes back inside range. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: chasing a huge candle without stop distance control.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "range_expansion",
        "breakout",
        "momentum",
        "volatility"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Expansion candle closes outside the range and follow-through holds.",
      "invalidation_logic": "Price retraces more than half and closes back inside range.",
      "common_mistake": "Chasing a huge candle without stop distance control."
    }
  },
  {
    "title": "Narrow Range Seven Breakout",
    "source_type": "strategy",
    "content_text": "Narrow Range Seven Breakout is a chart-pattern setup that appears when the current candle has the narrowest range of the last seven candles. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks the NR7 high or low with expansion. Invalidation occurs when price fails back inside the NR7 range. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: predicting direction before the range breaks.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "nr7",
        "volatility_contraction",
        "breakout",
        "compression"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks the NR7 high or low with expansion.",
      "invalidation_logic": "Price fails back inside the NR7 range.",
      "common_mistake": "Predicting direction before the range breaks."
    }
  },
  {
    "title": "Inside Bar Cluster Breakout",
    "source_type": "strategy",
    "content_text": "Inside Bar Cluster Breakout is a chart-pattern setup that appears when multiple inside bars compress within a mother candle. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks the mother candle range and closes beyond it. Invalidation occurs when price closes back inside the mother candle range. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: trading inside the cluster instead of waiting for expansion.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "inside_bar_cluster",
        "compression",
        "breakout",
        "continuation"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks the mother candle range and closes beyond it.",
      "invalidation_logic": "Price closes back inside the mother candle range.",
      "common_mistake": "Trading inside the cluster instead of waiting for expansion."
    }
  },
  {
    "title": "Outside Bar Reversal Structure",
    "source_type": "strategy",
    "content_text": "Outside Bar Reversal Structure is a chart-pattern setup that appears when a candle engulfs the prior range near a key support or resistance. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when follow-through breaks the outside bar in the reversal direction. Invalidation occurs when price breaks the opposite extreme of the outside bar. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: using outside bars without level context.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "outside_bar",
        "engulfing",
        "reversal",
        "price_action"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Follow-through breaks the outside bar in the reversal direction.",
      "invalidation_logic": "Price breaks the opposite extreme of the outside bar.",
      "common_mistake": "Using outside bars without level context."
    }
  },
  {
    "title": "Breakaway Base",
    "source_type": "strategy",
    "content_text": "Breakaway Base is a chart-pattern setup that appears when a long base suddenly breaks with strong momentum and does not immediately retest deeply. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price holds above the breakout base and forms continuation structure. Invalidation occurs when price closes back below breakout base. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: waiting for a perfect deep retest that never comes.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "breakaway_base",
        "accumulation",
        "momentum",
        "breakout"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price holds above the breakout base and forms continuation structure.",
      "invalidation_logic": "Price closes back below breakout base.",
      "common_mistake": "Waiting for a perfect deep retest that never comes."
    }
  },
  {
    "title": "Distribution Shelf Breakdown",
    "source_type": "strategy",
    "content_text": "Distribution Shelf Breakdown is a chart-pattern setup that appears when price forms a flat shelf after an advance but fails to continue higher. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when shelf support breaks with expanding sell volume. Invalidation occurs when price reclaims the shelf and closes above it. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: assuming every shelf is accumulation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "distribution_shelf",
        "breakdown",
        "bearish",
        "range"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Shelf support breaks with expanding sell volume.",
      "invalidation_logic": "Price reclaims the shelf and closes above it.",
      "common_mistake": "Assuming every shelf is accumulation."
    }
  },
  {
    "title": "Accumulation Shelf Breakout",
    "source_type": "strategy",
    "content_text": "Accumulation Shelf Breakout is a chart-pattern setup that appears when price forms a flat shelf after a decline and stops making lower lows. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when shelf resistance breaks with expanding demand. Invalidation occurs when price closes below shelf support. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: assuming every shelf is distribution.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "accumulation_shelf",
        "breakout",
        "bullish",
        "range"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Shelf resistance breaks with expanding demand.",
      "invalidation_logic": "Price closes below shelf support.",
      "common_mistake": "Assuming every shelf is distribution."
    }
  },
  {
    "title": "Descending Triangle Fakeout Long",
    "source_type": "strategy",
    "content_text": "Descending Triangle Fakeout Long is a chart-pattern setup that appears when a descending triangle breaks down but quickly reclaims support. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes back above support and breaks the last lower high. Invalidation occurs when price accepts below triangle support. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting the obvious breakdown after sellers are trapped.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "descending_triangle_fakeout",
        "trap",
        "bullish",
        "reclaim"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes back above support and breaks the last lower high.",
      "invalidation_logic": "Price accepts below triangle support.",
      "common_mistake": "Shorting the obvious breakdown after sellers are trapped."
    }
  },
  {
    "title": "Ascending Triangle Fakeout Short",
    "source_type": "strategy",
    "content_text": "Ascending Triangle Fakeout Short is a chart-pattern setup that appears when an ascending triangle breaks out but quickly falls back below resistance. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes back below resistance and breaks the last higher low. Invalidation occurs when price accepts above triangle resistance. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying the obvious breakout after buyers are trapped.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "ascending_triangle_fakeout",
        "trap",
        "bearish",
        "reclaim"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes back below resistance and breaks the last higher low.",
      "invalidation_logic": "Price accepts above triangle resistance.",
      "common_mistake": "Buying the obvious breakout after buyers are trapped."
    }
  },
  {
    "title": "Flag Failure Reversal",
    "source_type": "strategy",
    "content_text": "Flag Failure Reversal is a chart-pattern setup that appears when a flag continuation setup breaks opposite its expected direction. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks the flag invalidation side and follows through. Invalidation occurs when price returns into the flag and resumes original trend. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: refusing to exit because the original flag looked clean.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "flag_failure",
        "reversal",
        "trap",
        "price_action"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks the flag invalidation side and follows through.",
      "invalidation_logic": "Price returns into the flag and resumes original trend.",
      "common_mistake": "Refusing to exit because the original flag looked clean."
    }
  },
  {
    "title": "Wedge Throwover Reversal",
    "source_type": "strategy",
    "content_text": "Wedge Throwover Reversal is a chart-pattern setup that appears when price briefly breaks beyond a wedge boundary then reverses back inside. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price returns inside wedge and breaks the opposite internal structure. Invalidation occurs when price accepts beyond the throwover extreme. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: entering immediately on the throwover without reversal confirmation.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "throwover",
        "wedge",
        "reversal",
        "trap"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price returns inside wedge and breaks the opposite internal structure.",
      "invalidation_logic": "Price accepts beyond the throwover extreme.",
      "common_mistake": "Entering immediately on the throwover without reversal confirmation."
    }
  },
  {
    "title": "Terminal Triangle Breakout",
    "source_type": "strategy",
    "content_text": "Terminal Triangle Breakout is a chart-pattern setup that appears when price compresses at the end of a mature trend and momentum fades. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks opposite the prior trend with displacement. Invalidation occurs when price reclaims the triangle and resumes trend. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: assuming all triangles are continuation patterns.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "terminal_triangle",
        "compression",
        "breakout",
        "reversal"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks opposite the prior trend with displacement.",
      "invalidation_logic": "Price reclaims the triangle and resumes trend.",
      "common_mistake": "Assuming all triangles are continuation patterns."
    }
  },
  {
    "title": "Continuation Triangle In Trend",
    "source_type": "strategy",
    "content_text": "Continuation Triangle In Trend is a chart-pattern setup that appears when a triangle forms in the middle of a clean trend as temporary pause. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when price breaks in the direction of the higher-timeframe trend. Invalidation occurs when price breaks opposite the trend and holds. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: counter-trading a continuation triangle without reversal evidence.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "continuation_triangle",
        "trend",
        "compression",
        "breakout"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price breaks in the direction of the higher-timeframe trend.",
      "invalidation_logic": "Price breaks opposite the trend and holds.",
      "common_mistake": "Counter-trading a continuation triangle without reversal evidence."
    }
  },
  {
    "title": "Range Spring",
    "source_type": "strategy",
    "content_text": "Range Spring is a chart-pattern setup that appears when price dips below range support and quickly reclaims it. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes back above support and forms higher-low continuation. Invalidation occurs when price accepts below range support. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: buying the breakdown before reclaim.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "spring",
        "range",
        "bullish_reversal",
        "liquidity"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes back above support and forms higher-low continuation.",
      "invalidation_logic": "Price accepts below range support.",
      "common_mistake": "Buying the breakdown before reclaim."
    }
  },
  {
    "title": "Range Upthrust",
    "source_type": "strategy",
    "content_text": "Range Upthrust is a chart-pattern setup that appears when price pokes above range resistance and quickly returns below it. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes back below resistance and forms lower-high continuation. Invalidation occurs when price accepts above range resistance. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting before price returns below resistance.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "upthrust",
        "range",
        "bearish_reversal",
        "liquidity"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes back below resistance and forms lower-high continuation.",
      "invalidation_logic": "Price accepts above range resistance.",
      "common_mistake": "Shorting before price returns below resistance."
    }
  },
  {
    "title": "Multi Month Base Breakout",
    "source_type": "strategy",
    "content_text": "Multi Month Base Breakout is a chart-pattern setup that appears when price spends weeks or months building a wide accumulation base. Entry is considered only after the pattern gives a confirmed long trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes above long-term resistance with volume and accepts above it. Invalidation occurs when price closes back inside the base or below breakout level. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: underestimating volatility and using a stop that is too tight.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "multi_month_base",
        "breakout",
        "accumulation",
        "bullish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes above long-term resistance with volume and accepts above it.",
      "invalidation_logic": "Price closes back inside the base or below breakout level.",
      "common_mistake": "Underestimating volatility and using a stop that is too tight."
    }
  },
  {
    "title": "Multi Month Distribution Breakdown",
    "source_type": "strategy",
    "content_text": "Multi Month Distribution Breakdown is a chart-pattern setup that appears when price spends weeks or months distributing below resistance. Entry is considered only after the pattern gives a confirmed short trigger, not while price is still forming inside uncertain structure. Confirmation comes when price closes below long-term support with volume and accepts below it. Invalidation occurs when price reclaims support and returns into range. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: shorting before long-term support fails.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "multi_month_distribution",
        "breakdown",
        "distribution",
        "bearish"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Price closes below long-term support with volume and accepts below it.",
      "invalidation_logic": "Price reclaims support and returns into range.",
      "common_mistake": "Shorting before long-term support fails."
    }
  },
  {
    "title": "Crypto Weekend Range Break",
    "source_type": "strategy",
    "content_text": "Crypto Weekend Range Break is a chart-pattern setup that appears when crypto forms a thin-liquidity weekend range and later breaks it. Entry is considered only after the pattern gives a confirmed directional trigger, not while price is still forming inside uncertain structure. Confirmation comes when breakout holds after liquidity improves and spread remains normal. Invalidation occurs when price returns inside weekend range. Risk should be planned around the structural invalidation point and position size must be reduced if stop distance is too wide. Common mistake: trusting low-liquidity weekend wicks as confirmed breakouts.",
    "metadata": {
      "category": "chart_pattern",
      "tags": [
        "weekend_range",
        "crypto",
        "breakout",
        "liquidity"
      ],
      "priority": "high",
      "evidence_level": "education",
      "confirmation_logic": "Breakout holds after liquidity improves and spread remains normal.",
      "invalidation_logic": "Price returns inside weekend range.",
      "common_mistake": "Trusting low-liquidity weekend wicks as confirmed breakouts."
    }
  }
]
  $json$::jsonb) AS item(title text, source_type text, content_text text, metadata jsonb)
),
inserted_sources AS (
  INSERT INTO public.trading_knowledge_sources
    (user_id, title, source_type, content_text, metadata)
  SELECT
    NULL,
    p.title,
    CASE
      WHEN p.source_type IN ('note','article','video_transcript','pdf','strategy','post_trade') THEN p.source_type
      ELSE 'note'
    END,
    p.content_text,
    COALESCE(p.metadata, '{}'::jsonb) || jsonb_build_object(
      'scope', 'global',
      'seed', 'chart_pattern_knowledge_part1_2026_05_31',
      'part', 'chart_patterns_1'
    )
  FROM payload p
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.trading_knowledge_sources existing
    WHERE existing.user_id IS NULL
      AND existing.title = p.title
      AND existing.metadata->>'seed' = 'chart_pattern_knowledge_part1_2026_05_31'
  )
  RETURNING id, title, content_text, metadata
)
INSERT INTO public.trading_knowledge_chunks
  (source_id, user_id, chunk_index, content, tags, metadata)
SELECT
  s.id,
  NULL,
  0,
  s.content_text,
  ARRAY(SELECT jsonb_array_elements_text(COALESCE(s.metadata->'tags', '[]'::jsonb))),
  jsonb_build_object('scope', 'global', 'source_title', s.title, 'seed', 'chart_pattern_knowledge_part1_2026_05_31')
FROM inserted_sources s;

WITH eligible AS (
  SELECT
    s.id AS source_id,
    s.title,
    s.content_text,
    s.metadata,
    lower(COALESCE(s.metadata->>'priority', 'medium')) AS priority,
    lower(COALESCE(s.metadata->>'category', 'general')) AS category
  FROM public.trading_knowledge_sources s
  WHERE s.user_id IS NULL
    AND s.metadata->>'seed' = 'chart_pattern_knowledge_part1_2026_05_31'
    AND lower(COALESCE(s.metadata->>'priority', 'medium')) IN ('high', 'critical')
)
INSERT INTO public.trading_strategy_rules
  (user_id, source_id, rule_code, title, rule_text, category, severity, weight, metadata)
SELECT
  NULL,
  e.source_id,
  left('seed_chart_' || regexp_replace(lower(e.title), '[^a-z0-9]+', '_', 'g'), 96),
  e.title,
  e.content_text,
  e.category,
  CASE WHEN e.priority = 'critical' THEN 'critical' ELSE 'high' END,
  CASE WHEN e.priority = 'critical' THEN 24 ELSE 16 END,
  jsonb_build_object('scope', 'global', 'seed', 'chart_pattern_knowledge_part1_2026_05_31', 'part', 'chart_patterns_1')
FROM eligible e
WHERE NOT EXISTS (
  SELECT 1
  FROM public.trading_strategy_rules existing
  WHERE existing.rule_code = left('seed_chart_' || regexp_replace(lower(e.title), '[^a-z0-9]+', '_', 'g'), 96)
);

COMMIT;
