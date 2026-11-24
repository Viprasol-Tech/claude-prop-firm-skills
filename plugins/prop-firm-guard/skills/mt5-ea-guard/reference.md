# Sources (checked November 2026)

- `TimeCurrent()`: https://www.mql5.com/en/docs/dateandtime/timecurrent
- `TimeTradeServer()`: https://www.mql5.com/en/docs/dateandtime/timetradeserver
- `TimeGMT()`: https://www.mql5.com/en/docs/dateandtime/timegmt
- Deal properties (`DEAL_COMMISSION`, `DEAL_SWAP`, `DEAL_FEE`, deal types): https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties
- Account properties: https://www.mql5.com/en/docs/constants/environment_state/accountinformation
- FTMO equity definition and midnight CE(S)T: https://ftmo.com/en/trading-objectives/
- FTMO forbidden practices (2,000 requests a day): https://ftmo.com/en/forbidden-trading-practices/
- FTMO weekend and market breaks: https://ftmo.com/en/faq/do-i-have-to-close-my-positions-overnight-or-before-the-weekend/
- FundedNext EA policy: https://help.fundednext.com/en/articles/8020763-is-ea-allowed-in-fundednext
- EU and US daylight-saving rules in `PropGuard.mqh` were checked against the IANA tz database (Europe/Berlin, Europe/Athens, America/Chicago) every 30 minutes from 2024 to 2032.

Not stated in the MQL5 docs: exactly which costs `ACCOUNT_EQUITY` includes
and when a broker books entry commissions. Compare with the firm's
dashboard. The template has not been compiled in CI (no MetaEditor).
