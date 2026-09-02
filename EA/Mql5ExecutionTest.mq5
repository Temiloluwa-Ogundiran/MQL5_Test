#property strict
#include <Trade/Trade.mqh>

// Inputs
input string BackendURL = "https://mql5.temiloluwa.dev";
input int PollSec = 3;
input int StaleSec = 120;
input int DeviationPoints = 10;

CTrade trade;
string seen[];

// Check if signal already seen
bool Seen(string id)
{
   for (int i = 0; i < ArraySize(seen); i++)
   {
      if (seen[i] == id)
         return true;
   }
   return false;
}

// Mark signal as seen
void MarkSeen(string id)
{
   int n = ArraySize(seen);
   ArrayResize(seen, n + 1);
   seen[n] = id;
}

// Check staleness in UTC
bool IsStale(datetime gen)
{
   return (TimeGMT() - gen) > StaleSec;
}

// Minimal JSON helpers
string JStr(string js, string key)
{
   string q = "\"" + key + "\"";
   int p = StringFind(js, q);
   if (p < 0)
      return "";

   p = StringFind(js, ":", p);
   if (p < 0)
      return "";
   p++;

   while (p < StringLen(js) && StringGetCharacter(js, p) == 32)
      p++;

   if (StringGetCharacter(js, p) == '"')
   {
      int a = p + 1;
      int b = StringFind(js, "\"", a);
      if (b < 0)
         return "";
      return StringSubstr(js, a, b - a);
   }

   int b = p;
   while (b < StringLen(js) && StringGetCharacter(js, b) != 44 && StringGetCharacter(js, b) != 125)
      b++;

   string v = StringSubstr(js, p, b - p);
   StringTrimLeft(v);
   StringTrimRight(v);
   return v;
}

long JLong(string js, string key)
{
   return StringToInteger(JStr(js, key));
}

double JDbl(string js, string key)
{
   return StringToDouble(JStr(js, key));
}

datetime JTime(string js, string key)
{
   string s = JStr(js, key);
   if (s == "")
      return 0;

   StringReplace(s, "T", " ");
   StringReplace(s, "Z", "");

   int z = StringFind(s, "+");
   if (z > 0)
      s = StringSubstr(s, 0, z);

   int d = StringFind(s, ".");
   if (d > 0)
      s = StringSubstr(s, 0, d);

   StringReplace(s, "-", ".");
   StringTrim(s);

   return StringToTime(s);
}

// Forward declarations
void SendReport(string sid, ulong ord, ulong dea, ulong pos, double pr, double vol, int rc, string rdesc, string st, int mg);
void Execute(string sid, string sym, string dir, double lots, double sl, double tp, int mg, string cm);
void PollAndExecute();
void Reconcile();

// EA lifecycle
int OnInit()
{
   EventSetTimer(PollSec);
   Reconcile();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   PollAndExecute();
}

// Reconcile after restart: re-post deals from last 24h
void Reconcile()
{
   datetime from = TimeGMT() - 86400;
   if (!HistorySelect(from, TimeGMT()))
      return;

   for (int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong tk = HistoryDealGetTicket(i);
      int mg = (int)HistoryDealGetInteger(tk, DEAL_MAGIC);
      string cm = HistoryDealGetString(tk, DEAL_COMMENT);

      if (cm == "" && mg == 0)
         continue;

      ulong dea = tk;
      ulong ord = HistoryDealGetInteger(tk, DEAL_ORDER);
      ulong pos = HistoryDealGetInteger(tk, DEAL_POSITION_ID);
      double pr = HistoryDealGetDouble(tk, DEAL_PRICE);
      double vol = HistoryDealGetDouble(tk, DEAL_VOLUME);

      string sid = cm;
      long acc = AccountInfoInteger(ACCOUNT_LOGIN);

      string body = StringFormat(
         "{\"signal_id\":\"%s\",\"account_id\":%d,\"magic\":%d,\"order_ticket\":%d,\"deal_ticket\":%d,\"position_ticket\":%d,\"fill_price\":%f,\"filled_volume\":%f,\"retcode\":%d,\"retcode_description\":\"%s\",\"status\":\"%s\"}",
         sid, acc, mg, ord, dea, pos, pr, vol, 10009, "reconcile", "EXECUTED"
      );

      char d[];
      StringToCharArray(body, d);
      ArrayResize(d, ArraySize(d) - 1);

      char res[];
      string hdr = "Content-Type: application/json\r\n";
      string url = BackendURL + "/reports";
      WebRequest("POST", url, hdr, 5000, d, res, hdr);
   }
}

// Poll backend for next intent
void PollAndExecute()
{
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string url = BackendURL + "/intents/next?account_id=" + (string)login;

   char res[];
   string hdr;
   char data[];
   ArrayResize(data, 1);
   data[0] = 0;

   int r = WebRequest("GET", url, "", 10000, data, res, hdr);
   if (r != 200)
      return;

   string js = CharArrayToString(res);
   if (js == "")
      return;

   string sid = JStr(js, "signal_id");
   if (sid == "")
      return;

   if (Seen(sid))
      return;

   long aid = JLong(js, "account_id");
   if (aid != login)
      return;

   datetime gen = JTime(js, "generated_at");
   if (gen != 0 && IsStale(gen))
      return;

   string sym = JStr(js, "symbol");
   string dir = JStr(js, "direction");
   double lots = JDbl(js, "lots");
   double sl = JDbl(js, "sl");
   double tp = JDbl(js, "tp");
   int mg = (int)JLong(js, "magic_number");
   string cm = JStr(js, "comment");

   if (sym == "" || dir == "")
      return;

   MarkSeen(sid);
   Execute(sid, sym, dir, lots, sl, tp, mg, cm);
}

// Execute trade and report
void Execute(string sid, string sym, string dir, double lots, double sl, double tp, int mg, string cm)
{
   trade.SetExpertMagicNumber(mg);
   trade.SetDeviationInPoints(DeviationPoints);
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   // Pre-check stops level
   long stops = (long)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double pt = SymbolInfoDouble(sym, SYMBOL_POINT);
   if (pt == 0)
      pt = _Point;

   if (stops > 0)
   {
      if (sl != 0)
      {
         double d = MathAbs((dir == "BUY" ? bid : ask) - sl) / pt;
         if (d < stops)
         {
            SendReport(sid, 0, 0, 0, 0, 0, TRADE_RETCODE_INVALID_STOPS, "stops level", "REJECTED", mg);
            return;
         }
      }
      if (tp != 0)
      {
         double d = MathAbs((dir == "BUY" ? ask : bid) - tp) / pt;
         if (d < stops)
         {
            SendReport(sid, 0, 0, 0, 0, 0, TRADE_RETCODE_INVALID_STOPS, "stops level", "REJECTED", mg);
            return;
         }
      }
   }

   bool ok = false;
   if (dir == "BUY")
      ok = trade.Buy(lots, sym, 0, sl, tp, cm);
   else if (dir == "SELL")
      ok = trade.Sell(lots, sym, 0, sl, tp, cm);
   else
   {
      SendReport(sid, 0, 0, 0, 0, 0, TRADE_RETCODE_INVALID, "bad direction", "REJECTED", mg);
      return;
   }

   int rc = trade.ResultRetcode();
   string rdesc = trade.ResultRetcodeDescription();
   ulong ord = trade.ResultOrder();
   ulong dea = trade.ResultDeal();
   double pr = trade.ResultPrice();
   double vol = trade.ResultVolume();

   ulong pos = 0;
   if (dea != 0)
      pos = HistoryDealGetInteger(dea, DEAL_POSITION_ID);

   string st = (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || ok) ? "EXECUTED" : "REJECTED";
   if (vol > 0 && vol < lots)
      st = "PARTIAL";
   if (rc == TRADE_RETCODE_REQUOTE || rc == TRADE_RETCODE_PRICE_OFF)
      st = "REJECTED";

   SendReport(sid, ord, dea, pos, pr, vol, rc, rdesc, st, mg);
}

// Send report to backend
void SendReport(string sid, ulong ord, ulong dea, ulong pos, double pr, double vol, int rc, string rdesc, string st, int mg)
{
   long acc = AccountInfoInteger(ACCOUNT_LOGIN);
   string body = StringFormat(
      "{\"signal_id\":\"%s\",\"account_id\":%d,\"magic\":%d,\"order_ticket\":%d,\"deal_ticket\":%d,\"position_ticket\":%d,\"fill_price\":%f,\"filled_volume\":%f,\"retcode\":%d,\"retcode_description\":\"%s\",\"status\":\"%s\"}",
      sid, acc, mg, ord, dea, pos, pr, vol, rc, rdesc, st
   );

   char d[];
   StringToCharArray(body, d);
   ArrayResize(d, ArraySize(d) - 1);

   char res[];
   string hdr = "Content-Type: application/json\r\n";
   string url = BackendURL + "/reports";
   WebRequest("POST", url, hdr, 10000, d, res, hdr);
}
