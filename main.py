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
            raise FileNotFoundError("Нейросеть .pkl не найдена в корне!")
        self.model = joblib.load(CONFIG['MODEL_PATH'])
        self.headers = {'x-apisports-key': CONFIG['SPORTS_API_KEY']}

    def ask_gemini_auditor(self, match_name, odds, nn_res):
        """Платный Gemini - Финальный аудит по 'Уроку Челси'"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_API_KEY']}"
        prompt = f"""
        МАТЧ: {match_name} ({odds})
        НЕЙРОСЕТЬ: {nn_res['verdict']} (Вероятность: {nn_res['prob']}, Edge: {nn_res['edge']})
        
        Твоя роль: Аудитор системы ПКМ 2.0. 
        Примени 'Урок Челси': если фаворит (кэф < 1.7) переоценен буком, а Edge низкий - подтверди 🔴 Ловушку. 
        Выдай ОДНО короткое предложение.
        """
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=15).json()
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        except: return "Аудит в режиме ожидания..."

    def analyze_nn(self, h, x, a):
        """Математический движок с чистым округлением"""
        probs = self.model.predict_proba(np.array([[h, x, a]]))[0]
        outcomes = ['П1', 'X', 'П2']
        idx = np.argmax(probs)
        
        # Расчет перевеса (Edge) в % с округлением до 1 знака
        edge = round((probs[idx] - (1 / [h, x, a][idx])) * 100, 1)
        
        # Светофор Системы
        color = "🔴"
        if edge > 7: color = "🟢"
        elif edge > 3: color = "🟡"
        
        # Фильтр 'Урок Челси' (Lobby/Trap)
        if (h < 1.7 or a < 1.7) and edge < 5:
            color = "🔴 (TRAP)"
            
        return {
            "verdict": outcomes[idx], 
            "prob": f"{round(probs[idx]*100)}%", 
            "edge": f"{edge}%", 
            "color": color
        }

    def run(self):
        print("🌐 Запуск PCM_HYBRID_SCAN...")
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        f_url = f"https://v3.football.api-sports.io/fixtures?date={date_str}"
        
        try:
            fixtures = requests.get(f_url, headers=self.headers).json().get('response', [])
        except:
            print("❌ Ошибка API Sports")
            return
        
        # РАСШИРЕННАЯ ЛИНИЯ: Топ-Европа, Вторые лиги, Турция, Бразилия, Аргентина, МЛС, Кубки
        target_leagues = [39, 140, 135, 78, 61, 88, 94, 144, 179, 203, 253, 13, 10, 11, 62, 79, 141, 40, 103, 104, 2, 3, 30, 34] 
        
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
                # Берем первую доступную ставку (Match Winner)
                v = {val['value']: float(val['odd']) for val in bookie['bets'][0]['values']}
                h, x, a = v.get('Home', v.get('1')), v.get('Draw', v.get('X')), v.get('Away', v.get('2'))

                # 1. Анализ нейросетью
                nn_res = self.analyze_nn(h, x, a)
                
                # 2. Аудит Gemini (только если есть кэфы)
                audit = self.ask_gemini_auditor(m_name, f"{h}|{x}|{a}", nn_res)
                
                # Формируем данные для Терминала
                match_entry = {
                    "match": m_name,
                    "league": l_name,
                    "time": m_time,
                    "odds": f"{h} | {x} | {a}",
                    "analysis": nn_res,
                    "audit": audit
                }
                results.append(match_entry)
                
                # Отправка в Телеграм только качественных сигналов
                if nn_res['color'] != "🔴":
                    tg_msg = (f"{nn_res['color']} {m_name}\n"
                             f"🏆 {l_name} | 🕒 {m_time}\n"
                             f"📊 {h} | {x} | {a}\n"
                             f"🎯 {nn_res['verdict']} ({nn_res['prob']}) | Edge: {nn_res['edge']}\n"
                             f"🧐 {audit}")
                    requests.post(f"https://api.telegram.org/bot{CONFIG['TG_TOKEN']}/sendMessage", 
                                  json={"chat_id": CONFIG['TG_CHAT_ID'], "text": tg_msg})
                
                print(f"✅ Анализ завершен: {m_name}")
                time.sleep(0.3) # Платный API позволяет летать
                
            except Exception as e:
                print(f"⚠️ Пропуск матча: {e}")
                continue

        # Экспорт для index.html
        os.makedirs('web_export', exist_ok=True)
        with open('web_export/today_prognosis.json', 'w', encoding='utf-8') as out:
            json.dump(results, out, ensure_ascii=False, indent=4)
        print(f"🏁 Сбор данных окончен. Найдено матчей: {len(results)}")

if __name__ == "__main__":
    PcmHybridSystem().run()
