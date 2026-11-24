//+------------------------------------------------------------------+
//| PropGuard.mqh - daily-loss and max-loss guard for MT5 EAs         |
//| Part of claude-prop-firm-skills by Viprasol Tech Private Limited. |
//| MIT licence. Educational template: test on a demo account first. |
//+------------------------------------------------------------------+
// Usage in an EA:
//   #include "PropGuard.mqh"
//   CPropGuard guard;
//   int OnInit()
//   {
//      // FTMO 2-Step style: 100k, 5% daily from the balance at midnight CE(S)T, 10% static, act 1% early
//      if(!guard.Init(100000.0, 5.0, 10.0, false, FIRM_TZ_CET, 0, 0, 1.0)) return INIT_PARAMETERS_INCORRECT;
//      EventSetTimer(1);
//      return INIT_SUCCEEDED;
//   }
//   void OnTimer() { guard.Check(); }
//   void OnTick()
//   {
//      if(!guard.Check()) return;
//      // before every new order: worst-case loss if every stop is hit, from CURRENT prices,
//      // for all open positions plus the new order, including costs. Refuse orders without a stop.
//      // if(!guard.CanOpen(worstCaseLossMoney)) return;
//   }
//
// The guard compares EQUITY (floating P&L included) with
//   daily floor = day base - (daily% - buffer%) of initial; day base = balance at the firm's
//                 reset, rebuilt from deal history (or the higher of balance and equity, useMaxBase)
//   max floor   = initial - (max% - buffer%) of initial (static model only)
// When a floor is touched it closes every position and deletes every pending order
// on the account (all symbols, all EAs - deliberately), then blocks trading until
// the next reset (daily) or for good (max). Locks are saved in terminal global
// variables and flushed to disk at once. Trailing max-loss models need their own
// floor logic: see SKILL.md.
#include <Trade/Trade.mqh>

enum ENUM_FIRM_TZ
{
   FIRM_TZ_SERVER,     // the broker server's own midnight (TimeTradeServer) - "00:00 server time" firms
   FIRM_TZ_FIXED,      // fixed UTC offset, no daylight saving
   FIRM_TZ_CET,        // CET/CEST (UTC+1/+2), EU daylight saving - e.g. FTMO's midnight CE(S)T
   FIRM_TZ_EET,        // EET/EEST (UTC+2/+3), EU daylight saving
   FIRM_TZ_US_CENTRAL  // CST/CDT (UTC-6/-5), US daylight saving - e.g. 5 PM CT resets
};

class CPropGuard
{
private:
   CTrade       m_trade;
   double       m_initial, m_dailyPct, m_maxPct, m_bufferPct;
   bool         m_useMaxBase;
   ENUM_FIRM_TZ m_tz;
   int          m_fixedOffsetSec, m_resetSec;
   string       m_prefix;
   ulong        m_nextFlattenMs, m_backoffMs;

   static datetime LastSunday(int year, int month)          // 00:00 UTC of the month's last Sunday
   {
      MqlDateTime t; ZeroMemory(t);
      t.year = (month == 12) ? year + 1 : year; t.mon = (month == 12) ? 1 : month + 1; t.day = 1;
      datetime d = StructToTime(t) - 86400;
      MqlDateTime x; TimeToStruct(d, x);
      return d - x.day_of_week * 86400;
   }
   static datetime NthSunday(int year, int month, int n)    // 00:00 UTC of the n-th Sunday
   {
      MqlDateTime t; ZeroMemory(t);
      t.year = year; t.mon = month; t.day = 1;
      datetime d = StructToTime(t);
      MqlDateTime x; TimeToStruct(d, x);
      return d + ((7 - x.day_of_week) % 7 + 7 * (n - 1)) * 86400;
   }
   int OffsetSec(datetime gmt)
   {
      MqlDateTime g; TimeToStruct(gmt, g);
      if(m_tz == FIRM_TZ_CET || m_tz == FIRM_TZ_EET)
      {
         // EU summer time: last Sunday of March 01:00 UTC to last Sunday of October 01:00 UTC
         datetime s = LastSunday(g.year, 3) + 3600, e = LastSunday(g.year, 10) + 3600;
         return (m_tz == FIRM_TZ_CET ? 3600 : 7200) + ((gmt >= s && gmt < e) ? 3600 : 0);
      }
      if(m_tz == FIRM_TZ_US_CENTRAL)
      {
         // US daylight time: 2nd Sunday of March 08:00 UTC to 1st Sunday of November 07:00 UTC
         datetime s = NthSunday(g.year, 3, 2) + 8 * 3600, e = NthSunday(g.year, 11, 1) + 7 * 3600;
         return -6 * 3600 + ((gmt >= s && gmt < e) ? 3600 : 0);
      }
      return m_fixedOffsetSec;
   }
   // "Firm clock": wall time in the firm's zone. TimeGMT/TimeTradeServer use the PC clock: keep it on NTP.
   datetime FirmNow()
   {
      if(m_tz == FIRM_TZ_SERVER) return TimeTradeServer();
      datetime gmt = TimeGMT();
      return gmt + OffsetSec(gmt);
   }
   long TradingDay()           { return (long)((FirmNow() - m_resetSec) / 86400); }
   long SecondsSinceReset()    { return (long)((FirmNow() - m_resetSec) % 86400); }

   // Balance at the last reset = balance now minus today's trading results (deals since the reset).
   double BalanceAtReset()
   {
      datetime serverNow = TimeTradeServer();
      datetime resetServer = serverNow - (datetime)SecondsSinceReset();
      double bal = AccountInfoDouble(ACCOUNT_BALANCE);
      if(!HistorySelect(resetServer, serverNow + 3600)) { Print("PropGuard: HistorySelect failed"); return bal; }
      for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
      {
         ulong deal = HistoryDealGetTicket(i);
         if(deal == 0) continue;
         long type = HistoryDealGetInteger(deal, DEAL_TYPE);
         if(type == DEAL_TYPE_BALANCE || type == DEAL_TYPE_CREDIT) continue;   // deposits/withdrawals are not P&L
         bal -= HistoryDealGetDouble(deal, DEAL_PROFIT) + HistoryDealGetDouble(deal, DEAL_COMMISSION)
              + HistoryDealGetDouble(deal, DEAL_SWAP) + HistoryDealGetDouble(deal, DEAL_FEE);
      }
      return bal;
   }
   double GV(string key, double def)
   {
      string n = m_prefix + key;
      return GlobalVariableCheck(n) ? GlobalVariableGet(n) : def;
   }
   void SetGV(string key, double v) { GlobalVariableSet(m_prefix + key, v); GlobalVariablesFlush(); }

   void FlattenAll(string why)
   {
      ulong now = GetTickCount64();
      if(now < m_nextFlattenMs) return;                        // back off: never flood the server
      PrintFormat("PropGuard: %s - closing all positions and orders", why);
      bool failed = false;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket != 0 && !m_trade.PositionClose(ticket))
         { failed = true; PrintFormat("PropGuard: close %I64u failed rc=%u", ticket, m_trade.ResultRetcode()); }
      }
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         ulong ticket = OrderGetTicket(i);
         if(ticket != 0 && !m_trade.OrderDelete(ticket))
         { failed = true; PrintFormat("PropGuard: delete %I64u failed rc=%u", ticket, m_trade.ResultRetcode()); }
      }
      // failures (market closed, requotes): retry after 3 s, 6 s, 12 s ... up to 5 minutes
      m_backoffMs = failed ? (ulong)MathMin((double)m_backoffMs * 2.0, 300000.0) : 3000;
      m_nextFlattenMs = now + (failed ? m_backoffMs : 0);
   }

   void StartDay(long day, double bal, double eq)
   {
      double base = BalanceAtReset();
      if(m_useMaxBase)
      {
         if(SecondsSinceReset() <= 120) base = MathMax(base, eq);   // captured right at the reset
         else
         {
            // Equity at the reset is unknown after a restart: use the strictest value we know.
            base = MathMax(base, MathMax(bal, eq));
            Print("PropGuard: started after the reset; equity at the reset is unknown - check the firm dashboard");
         }
      }
      SetGV("day", (double)day);
      SetGV("base", base);
      SetGV("dayLocked", 0);
      PrintFormat("PropGuard: trading day %I64d, base %.2f, daily floor %.2f, max floor %.2f", day, base, DailyFloor(), MaxFloor());
   }

public:
   // initial: starting balance. dailyPct / maxPct: % of initial (0 disables).
   // useMaxBase: day base = max(balance, equity) at the reset (else balance).
   // tz + fixedOffsetHours: the firm's clock; resetHour: the firm's reset hour on that clock.
   // bufferPct: act this many % of initial BEFORE the real limit (slippage, spread, costs).
   bool Init(double initial, double dailyPct, double maxPct, bool useMaxBase,
             ENUM_FIRM_TZ tz, double fixedOffsetHours, int resetHour, double bufferPct)
   {
      if(initial <= 0 || bufferPct < 0 || resetHour < 0 || resetHour > 23 ||
         (dailyPct > 0 && bufferPct >= dailyPct) || (maxPct > 0 && bufferPct >= maxPct))
      { Print("PropGuard: invalid parameters (buffer must be smaller than each limit)"); return false; }
      m_initial = initial; m_dailyPct = dailyPct; m_maxPct = maxPct; m_useMaxBase = useMaxBase;
      m_tz = tz; m_fixedOffsetSec = (int)MathRound(fixedOffsetHours * 3600); m_resetSec = resetHour * 3600;
      m_bufferPct = bufferPct; m_nextFlattenMs = 0; m_backoffMs = 3000;
      // one state per account and server (global variable names are limited to 63 characters)
      m_prefix = StringFormat("PG_%s_%I64d_", StringSubstr(AccountInfoString(ACCOUNT_SERVER), 0, 24),
                              AccountInfoInteger(ACCOUNT_LOGIN));
      m_trade.SetDeviationInPoints(50);
      Check();
      return true;
   }

   double DailyFloor() { return GV("base", m_initial) - m_initial * (m_dailyPct - m_bufferPct) / 100.0; }
   double MaxFloor()   { return m_initial * (1.0 - (m_maxPct - m_bufferPct) / 100.0); }

   // false = trading must stop. Call on every tick AND on a timer (timers fire without ticks).
   bool Check()
   {
      double bal = AccountInfoDouble(ACCOUNT_BALANCE);
      double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
      long day = TradingDay();
      if((long)GV("day", -1) != day) StartDay(day, bal, eq);
      bool flat = PositionsTotal() + OrdersTotal() == 0;
      if(flat) { m_backoffMs = 3000; m_nextFlattenMs = 0; }
      // max loss first: it must trigger even while a daily lock is active
      if(m_maxPct > 0 && GV("maxLocked", 0) == 0 && eq <= MaxFloor())
         SetGV("maxLocked", 1);
      if(GV("maxLocked", 0) > 0) { if(!flat) FlattenAll(StringFormat("max loss lock (equity %.2f)", eq)); return false; }
      if(m_dailyPct > 0 && GV("dayLocked", 0) == 0 && eq <= DailyFloor())
         SetGV("dayLocked", 1);
      if(GV("dayLocked", 0) > 0) { if(!flat) FlattenAll(StringFormat("daily lock (equity %.2f)", eq)); return false; }
      return true;
   }

   // worstCaseLoss: money lost if every stop is hit from CURRENT prices (all open positions
   // plus the new order), including commissions. The caller must refuse orders without a stop.
   bool CanOpen(double worstCaseLoss)
   {
      if(!Check() || worstCaseLoss < 0) return false;
      double eq = AccountInfoDouble(ACCOUNT_EQUITY);
      return (m_dailyPct <= 0 || eq - worstCaseLoss > DailyFloor()) &&
             (m_maxPct   <= 0 || eq - worstCaseLoss > MaxFloor());
   }
};
