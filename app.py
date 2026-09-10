import io
import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import streamlit as st
import pandas as pd
import pathlib
import subprocess
import subprocess
subprocess.run([sys.executable, "-m", "playwright", "install"])
st.set_page_config(page_title="DACH B2B Lead Generator", layout="wide")

st.title("🎯 DACH B2B Lead Generator")
st.markdown("Инструмент автоматического сбора и обогащения B2B-лидов с Google Maps под немецкоязычный рынок (DE/AT/CH).")

st.sidebar.header("Параметры поиска")

niche = st.sidebar.text_input("Ниша / Ключевое слово", value="Autowerkstatt")
city = st.sidebar.text_input("Город", value="Dortmund")
language = st.sidebar.selectbox("Язык поиска", ["Немецкий (DE)", "Английский (EN)", "Русский (RU)"])
limit = st.sidebar.slider("Лимит записей", min_value=10, max_value=200, value=50, step=10)

start_button = st.sidebar.button("🚀 Запустить сбор баз")

st.divider()

csv_file = pathlib.Path("leads.csv")

if start_button:
    st.info(f"Запускаем поиск: **{niche}** в городе **{city}** (лимит: {limit})...")
    
    try:
        with st.spinner("Скрипт собирает данные... Пожалуйста, подождите."):
            search_query = f"{niche} {city}"
            result = subprocess.run(
                [sys.executable, "main.py", search_query, str(limit)],
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
        
        with st.expander("Показать журнал парсера", expanded=True):
            st.code(result.stdout or "Парсер ничего не сообщил")

            if result.stderr:
                st.code(result.stderr)

        if result.returncode == 0:
            st.success("Сбор успешно завершен!")
        else:
            st.error("Произошла ошибка при выполнении парсера.")
            st.code(result.stderr)
    except Exception as e:
        st.error(f"Ошибка запуска: {e}")

if csv_file.exists():
    st.subheader("📊 Собранные данные")
    
    # Читаем собранный CSV
    df = pd.read_csv(csv_file, sep=";", encoding="utf-8-sig", on_bad_lines="skip", engine="python")
    st.dataframe(df, use_container_width=True)

    # Конвертируем DataFrame в Excel (.xlsx) в памяти
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Leads")

    # Кнопка скачивания XLSX
    st.download_button(
        label="📥 Скачать базу в Excel (.xlsx)",
        data=buffer.getvalue(),
        file_name=f"leads_{city}_{niche}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    