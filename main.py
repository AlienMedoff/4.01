import joblib, os, requests, json, math, time
import numpy as np
from datetime import datetime, timezone

# Конфигурация
CONFIG = {
    'SPORTS_API_KEY': os.getenv('SPORTS_API_KEY'),
    'GEMINI_API_KEY': os.getenv('GEMINI_API_KEY'),
    'TG_TOKEN': os.getenv('TG_TOKEN'),
    'TG_CHAT_ID': os.getenv('TG_CHAT_ID'),
    'MODEL_PATH': 'football_model.pkl'
}

class PcmHybridSystem:
    def __init__(self):
        if not os.path.exists(CONFIG['MODEL_PATH']):
            raise FileNotFoundError("Нейросеть .pkl не найдена!")
        self.model = joblib.load(CONFIG['MODEL_PATH'])
        self.headers = {'x-apisports-key': CONFIG['SPORTS_API_KEY']}

    def ask_gemini_auditor(self, match_name, odds, nn_res):
        """Платный Gemini - Финальный фильтр (Урок Челси)"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_API_KEY']}"
        prompt = f"""
        МАТЧ: {match_name} ({odds})
        НЕЙРОСЕТЬ ГОВОРИТ: {nn_res['verdict']} (Вероятность: {nn_res['prob']}, Перевес: {nn_res['edge']})
        
        Твоя роль: Аудитор системы ПКМ 2.0. 
        Примени 'Урок Челси': если фаворит переоценен буком, а нейронка дает низкий Edge - подтверди 🔴 Ловушку. 
        Выдай ОДНО короткое предложение-вердикт.
        """
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=15).json()
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        except: return "Аудит временно недоступен (Billing/Limit)"

    def analyze_nn(self, h, x, a):
        # Математический движок
        probs = self.model.predict_proba(np.array([[h, x, a]]))[0]
        outcomes = ['П1', 'X', 'П2']
        idx = np.argmax(probs)
        edge = probs[idx] - (1 / [h, x, a][idx])
        
        # Светофор
        color = "🔴"
        if edge > 0.07: color = "🟢"
        elif edge > 0.03: color = "🟡"
        
        # Жесткая проверка на ловушку
        if (h < 1.7 or a < 1.7) and edge < 0.05:
            color = "🔴 (TRAP)"
            
        return {
            "verdict": outcomes[idx], 
            "prob": f"{round(probs[idx]*100)}%", 
            "edge": f"{round(edge*100, 1)}%", 
            "color": color
        }

    def run(self):
        print("🌐 Запуск глубокого сканирования линии...")
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        f_url = f"https://v3.football.api-sports.io/fixtures?date={date_str}"
        fixtures = requests.get(f_url, headers=self.headers).json().get('response', [])
        
        # МАКСИМАЛЬНАЯ ЛИНИЯ (Топ + Вторые дивизионы + Юж. Америка + Турция/Греция)
        target_leagues = [39, 140, 135, 78, 61, 88, 94, 144, 179, 203, 253, 13, 10, 11, 62, 79, 141, 40, 141, 103, 104, 2] 
        
        results = []
        for f in fixtures:
            if f['league']['id'] not in target_leagues: continue
            
            try:
                m_id = f['fixture']['id']
                m_name = f"{f['teams']['home']['name']} - {f['teams']['away']['name']}"
                l_name = f"{f['league']['name']} ({f['league']['country']})"
                m_time = datetime.fromisoformat(f['fixture']['date'].replace('Z', '+00:00')).strftime('%H:%M')
                
                # Получаем коэффициенты
                o_res = requests.get(f"https://v3.football.api-sports.io/odds?fixture={m_id}", headers=self.headers).json()
                if not o_res.get('response'): continue
                
                bookie = o_res['response'][0]['bookmakers'][0]
                v = {val['value']: float(val['odd']) for val in bookie['bets'][0]['values']}
                h, x, a = v.get('Home', v.get('1')), v.get('Draw', v.get('X')), v.get('Away', v.get('2'))

                # 1. Анализ нейронкой
                nn_res = self.analyze_nn(h, x, a)
                
                # 2. Аудит Gemini (платный)
                audit = self.ask_gemini_auditor(m_name, f"{h}|{x}|{a}", nn_res)
                
                # Данные для HTML Терминала
                match_data = {
                    "match": m_name,
                    "league": l_name,
                    "time": m_time,
                    "odds": f"{h} | {x} | {a}",
                    "analysis": nn_res,
                    "audit": audit
                }
                results.append(match_data)
                
                # В Телеграм только сочные варианты (Зеленые, Желтые или Ловушки)
                msg = (f"{nn_res['color']} {m_name}\n"
                       f"🏆 {l_name} | 🕒 {m_time}\n"
                       f"📊 {h} | {x} | {a}\n"
                       f"🎯 {nn_res['verdict']} ({nn_res['prob']}) | Edge: {nn_res['edge']}\n"
                       f"🧐 {audit}")
                
                print(f"✅ Готово: {m_name}")
                requests.post(f"https://api.telegram.org/bot{CONFIG['TG_TOKEN']}/sendMessage", json={"chat_id": CONFIG['TG_CHAT_ID'], "text": msg})
                
                time.sleep(0.5) # На платном API летает
                
            except Exception as e:
                print(f"⚠️ Ошибка в матче: {e}")
                continue

        # Сохранение для Киберпанк-терминала
        os.makedirs('web_export', exist_ok=True)
        with open('web_export/today_prognosis.json', 'w', encoding='utf-8') as out:
            json.dump(results, out, ensure_ascii=False, indent=4)
        print(f"🏁 Сбор завершен. Обработано {len(results)} матчей.")

if __name__ == "__main__":
    PcmHybridSystem().run()
