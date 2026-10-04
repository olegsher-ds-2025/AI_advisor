# Intraday Intensity Index (IIX)

IIX measures where each bar closes inside its high-low range, weighted by volume. A close near
the high on heavy volume reads as buying pressure, a close near the low as selling pressure.

```
IIX raw = (2 * Close - High - Low) / (High - Low) * Volume
```

`quant/indicators.py` publishes it as `100 * sum(raw, 21) / sum(Volume, 21)`, which bounds the
value to -100..100 so symbols are comparable. Bars with `High == Low` contribute 0.

## Reading it

- **Breakout confirmation:** a break above resistance with IIX rising into positive territory
  suggests real buying behind the move; the mirror case confirms a breakdown.
- **Divergence:** higher price highs with lower IIX highs suggest distribution; lower price lows
  with higher IIX lows suggest accumulation.
- **Zero line:** IIX hovering near zero means balanced buying and selling, typical of choppy
  sideways markets.
- **Trend filter:** pair it with a 50 or 200 EMA and take only signals aligned with that trend.

## Versus related indicators

| Indicator | Driver | Note |
|---|---|---|
| IIX | Close position in the high-low range, times volume | Best at end-of-bar pressure |
| Accumulation/Distribution | Same idea, different scaling | Cumulative volume flow |
| Chaikin Money Flow | A/D divided by volume over a window (usually 21) | Oscillates between -1 and +1 |
