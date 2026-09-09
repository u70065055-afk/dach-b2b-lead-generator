print("Скрипт запущен...", flush=True)

import random
import re
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import quote_plus

try:
    print("Импортируем pandas и Playwright...", flush=True)

    import pandas as pd
    from playwright.sync_api import (
        BrowserContext,
        Locator,
        Page,
        TimeoutError as PlaywrightTimeoutError,
        sync_playwright,
    )
except ImportError as error:
    print("\nОШИБКА: не установлена необходимая библиотека.", flush=True)
    print(f"Подробности: {error}", flush=True)
    print("\nВыполните в терминале:", flush=True)
    print("python -m pip install pandas playwright", flush=True)
    print("python -m playwright install chromium", flush=True)
    input("\nНажмите Enter для завершения...")
    raise SystemExit(1)


SEARCH_QUERY = "Autowerkstatt Dortmund"
TARGET_LISTINGS = 50
OUTPUT_FILE = Path("leads.csv")
HEADLESS = False
DEFAULT_TIMEOUT_MS = 15_000


def log(message: str) -> None:
    print(message, flush=True)


def pause(min_seconds: float = 0.7, max_seconds: float = 1.8) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def safe_text(locator: Locator, timeout: int = 3_000) -> str:
    try:
        if locator.count() > 0:
            return " ".join(
                locator.first.inner_text(timeout=timeout).split()
            )
    except Exception:
        pass

    return ""


def safe_attribute(
    locator: Locator,
    attribute: str,
    timeout: int = 3_000,
) -> str:
    try:
        if locator.count() > 0:
            return (
                locator.first.get_attribute(
                    attribute,
                    timeout=timeout,
                )
                or ""
            )
    except Exception:
        pass

    return ""


def clean_button_value(
    value: str,
    prefixes: tuple[str, ...],
) -> str:
    value = " ".join(value.split())

    for prefix in prefixes:
        if value.lower().startswith(prefix.lower()):
            value = value[len(prefix):].strip(" :")

    return value


def accept_consent(page: Page) -> None:
    log("Проверяем окно согласия Google...")

    selectors = [
        'button:has-text("Alle akzeptieren")',
        'button:has-text("Accept all")',
        'button:has-text("Ich stimme zu")',
        'button:has-text("I agree")',
        'form[action*="consent"] button',
    ]

    for selector in selectors:
        try:
            button = page.locator(selector)

            if button.count() > 0 and button.first.is_visible():
                log("Найдено окно согласия. Нажимаем кнопку...")
                button.first.click(timeout=4_000)
                page.wait_for_timeout(1_500)
                log("Окно согласия закрыто.")
                return
        except Exception:
            continue

    log("Окно согласия не найдено или уже было принято.")


def collect_listing_urls(
    page: Page,
    target: int,
) -> list[str]:
    log("Ищем панель с результатами...")

    try:
        feed = page.locator('div[role="feed"]').first
        feed.wait_for(state="visible", timeout=20_000)
        log("Панель результатов найдена.")
    except PlaywrightTimeoutError:
        log(
            "Стандартная панель не найдена. "
            "Пробуем альтернативный селектор..."
        )

        feed = page.locator(
            'div[aria-label*="Ergebnisse"], '
            'div[aria-label*="Results"]'
        ).first

        feed.wait_for(state="visible", timeout=10_000)
        log("Панель результатов найдена альтернативным способом.")

    collected_urls: dict[str, None] = {}
    unchanged_rounds = 0
    previous_count = 0

    log("Начинаем прокрутку результатов...")

    for scroll_number in range(1, 81):
        log(f"Прокрутка №{scroll_number}. Ищем элементы...")

        try:
            links = page.locator('a[href*="/maps/place/"]')
            links_count = links.count()

            log(f"На странице обнаружено ссылок: {links_count}")

            for index in range(links_count):
                try:
                    href = links.nth(index).get_attribute("href")

                    if href and "/maps/place/" in href:
                        collected_urls[href] = None
                except Exception as error:
                    log(
                        f"Не удалось прочитать ссылку №{index + 1}: "
                        f"{error}"
                    )

        except Exception as error:
            log(f"Ошибка во время поиска ссылок: {error}")

        current_count = len(collected_urls)
        log(f"Найдено уникальных записей: {current_count}/{target}")

        if current_count >= target:
            log("Необходимое количество записей собрано.")
            break

        if current_count == previous_count:
            unchanged_rounds += 1
            log(
                "Новых записей после прокрутки нет. "
                f"Попытка {unchanged_rounds}/10."
            )
        else:
            unchanged_rounds = 0

        previous_count = current_count

        try:
            end_message = page.get_by_text(
                re.compile(
                    r"Du hast das Ende der Liste erreicht|"
                    r"You(?:'|’)?ve reached the end of the list",
                    re.IGNORECASE,
                )
            )

            if (
                end_message.count() > 0
                and end_message.first.is_visible()
            ):
                log("Google сообщил, что достигнут конец списка.")
                break
        except Exception:
            pass

        if unchanged_rounds >= 10:
            log(
                "После 10 прокруток новые записи не появились. "
                "Останавливаем прокрутку."
            )
            break

        try:
            log("Прокручиваем левую панель вниз...")

            feed.evaluate(
                """
                element => {
                    element.scrollBy({
                        top: Math.max(
                            element.clientHeight * 0.9,
                            800
                        ),
                        behavior: "smooth"
                    });
                }
                """
            )
        except Exception as error:
            log(
                f"Обычная прокрутка не сработала: {error}. "
                "Пробуем клавишу End..."
            )

            try:
                feed.press("End")
            except Exception as second_error:
                log(
                    "Не удалось прокрутить панель: "
                    f"{second_error}"
                )

        pause(1.2, 2.4)

    urls = list(collected_urls.keys())[:target]
    log(f"Сбор ссылок завершен. Всего ссылок: {len(urls)}")

    return urls


def parse_rating_and_reviews(
    page: Page,
) -> tuple[str, str]:
    rating = ""
    review_count = ""
    possible_values: list[str] = []

    selectors = [
        'div.F7nice span[aria-hidden="true"]',
        'button[aria-label*="Rezension"]',
        'button[aria-label*="Bewertung"]',
        'button[aria-label*="review"]',
        '[aria-label*="Sterne"]',
        '[aria-label*="stars"]',
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)
            elements_count = min(locator.count(), 10)

            for index in range(elements_count):
                element = locator.nth(index)
                text = safe_text(element)
                aria_label = safe_attribute(element, "aria-label")

                if text:
                    possible_values.append(text)

                if aria_label:
                    possible_values.append(aria_label)

        except Exception:
            continue

    combined = " | ".join(possible_values)

    rating_patterns = [
        r"([0-5][.,]\d)\s*(?:Sterne|stars?)",
        r"([0-5][.,]\d)",
    ]

    for pattern in rating_patterns:
        rating_match = re.search(
            pattern,
            combined,
            re.IGNORECASE,
        )

        if rating_match:
            candidate = rating_match.group(1).replace(",", ".")

            try:
                if 0 <= float(candidate) <= 5:
                    rating = candidate
                    break
            except ValueError:
                pass

    review_match = re.search(
        r"([\d.\s,]+)\s*"
        r"(?:Rezensionen?|Bewertungen?|reviews?)",
        combined,
        re.IGNORECASE,
    )

    if review_match:
        review_count = re.sub(
            r"\D",
            "",
            review_match.group(1),
        )

    if not review_count:
        parenthesized_numbers = re.findall(
            r"\(([\d.\s,]+)\)",
            combined,
        )

        if parenthesized_numbers:
            review_count = re.sub(
                r"\D",
                "",
                parenthesized_numbers[0],
            )

    return rating, review_count


def extract_listing(
    page: Page,
    url: str,
) -> dict[str, str]:
    result = {
        "Company Name": "",
        "Phone Number": "",
        "Website URL": "",
        "Full Address": "",
        "Rating": "",
        "Review Count": "",
        "Google Maps URL": url,
    }

    log("Открываем страницу компании...")

    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30_000,
        )

        log("Страница открыта. Ждем название компании...")

        page.locator("h1").first.wait_for(
            state="visible",
            timeout=15_000,
        )

        pause(0.8, 1.7)

    except PlaywrightTimeoutError:
        log("Превышено время ожидания страницы компании.")

    except Exception as error:
        log(f"Не удалось открыть компанию: {error}")

    try:
        result["Company Name"] = safe_text(
            page.locator("h1")
        )
        log(
            "Название: "
            f"{result['Company Name'] or 'не найдено'}"
        )
    except Exception as error:
        log(f"Ошибка получения названия: {error}")

    try:
        address_button = page.locator(
            'button[data-item-id="address"], '
            'button[aria-label^="Adresse:"], '
            'button[aria-label^="Address:"]'
        )

        address = safe_attribute(
            address_button,
            "aria-label",
        )

        if not address:
            address = safe_text(address_button)

        result["Full Address"] = clean_button_value(
            address,
            ("Adresse", "Address"),
        )

        log(
            "Адрес: "
            f"{result['Full Address'] or 'не найден'}"
        )

    except Exception as error:
        log(f"Ошибка получения адреса: {error}")

    try:
        phone_button = page.locator(
            'button[data-item-id^="phone:"], '
            'button[aria-label^="Telefon:"], '
            'button[aria-label^="Phone:"]'
        )

        phone = safe_attribute(
            phone_button,
            "aria-label",
        )

        if not phone:
            phone = safe_text(phone_button)

        result["Phone Number"] = clean_button_value(
            phone,
            ("Telefon", "Phone"),
        )

        log(
            "Телефон: "
            f"{result['Phone Number'] or 'не найден'}"
        )

    except Exception as error:
        log(f"Ошибка получения телефона: {error}")

    try:
        website_link = page.locator(
            'a[data-item-id="authority"], '
            'a[aria-label^="Website:"], '
            'a[aria-label^="Webseite:"]'
        )

        result["Website URL"] = safe_attribute(
            website_link,
            "href",
        )

        log(
            "Сайт: "
            f"{result['Website URL'] or 'не найден'}"
        )

    except Exception as error:
        log(f"Ошибка получения сайта: {error}")

    try:
        rating, review_count = parse_rating_and_reviews(page)
        result["Rating"] = rating
        result["Review Count"] = review_count

        log(
            f"Рейтинг: {rating or 'не найден'}, "
            f"отзывов: {review_count or 'не найдено'}"
        )

    except Exception as error:
        log(f"Ошибка получения рейтинга: {error}")

    return result


def create_context(browser) -> BrowserContext:
    log("Создаем контекст браузера...")

    context = browser.new_context(
        locale="de-DE",
        timezone_id="Europe/Berlin",
        viewport={
            "width": 1440,
            "height": 900,
        },
        color_scheme="light",
        extra_http_headers={
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        },
    )

    context.set_default_timeout(DEFAULT_TIMEOUT_MS)
    log("Контекст браузера создан.")

    return context


def save_results(
    results: list[dict[str, str]],
) -> None:
    log(f"Сохраняем найденные записи: {len(results)}")

    columns = [
        "Company Name",
        "Phone Number",
        "Website URL",
        "Full Address",
        "Rating",
        "Review Count",
        "Google Maps URL",
    ]

    dataframe = pd.DataFrame(
        results,
        columns=columns,
    )

    if not dataframe.empty:
        dataframe.drop_duplicates(
            subset=[
                "Company Name",
                "Full Address",
            ],
            keep="first",
            inplace=True,
        )

        dataframe.sort_values(
            by="Company Name",
            key=lambda series: series.str.lower(),
            inplace=True,
        )

    dataframe.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    log(
        f"Файл сохранен: {OUTPUT_FILE.resolve()} "
        f"(строк: {len(dataframe)})"
    )


def main() -> None:
    SEARCH_QUERY = sys.argv[1] if len(sys.argv) > 1 else "Autowerkstatt Dortmund"
    TARGET_LISTINGS = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    results: list[dict[str, str]] = []
    browser = None
    context = None

    log("=" * 60)
    log("Google Maps scraper")
    log(f"Поисковый запрос: {SEARCH_QUERY}")
    log(f"Цель: {TARGET_LISTINGS} компаний")
    log(f"Файл результата: {OUTPUT_FILE.resolve()}")
    log("=" * 60)

    with sync_playwright() as playwright:
        try:
            log("Запуск браузера Chromium...")

            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="de-DE",
            )

            log("Браузер запущен.")

            page = context.new_page()

            search_url = (
                "https://www.google.com/maps/search/"
                f"{quote_plus(SEARCH_QUERY)}?hl=de"
            )

            page.goto(
                search_url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )

            log(f"Google Maps открыт: {page.url}")

            accept_consent(page)
            pause(1.5, 2.8)

            listing_urls = collect_listing_urls(
                page,
                TARGET_LISTINGS,
            )

            if not listing_urls:
                log(
                    "ОШИБКА: компании не найдены. "
                    "Проверьте окно браузера на наличие CAPTCHA "
                    "или запроса согласия."
                )

                save_results(results)
                return

            log(
                f"Начинаем извлечение данных из "
                f"{len(listing_urls)} компаний."
            )

            for index, listing_url in enumerate(
                listing_urls,
                start=1,
            ):
                log("")
                log("-" * 60)
                log(
                    f"Обрабатываем компанию "
                    f"{index}/{len(listing_urls)}"
                )
                log(f"URL: {listing_url}")

                try:
                    listing = extract_listing(
                        page,
                        listing_url,
                    )

                    if listing["Company Name"]:
                        results.append(listing)
                        log(
                            f"Запись добавлена. "
                            f"Всего записей: {len(results)}"
                        )
                    else:
                        log(
                            "Запись пропущена: "
                            "название компании не найдено."
                        )

                except Exception as error:
                    log(
                        "Ошибка обработки компании: "
                        f"{error}"
                    )
                    traceback.print_exc()

                if index % 5 == 0:
                    log(
                        "Промежуточное сохранение результатов..."
                    )
                    save_results(results)

                pause(1.0, 2.4)

            log("Все доступные компании обработаны.")

        except PlaywrightTimeoutError as error:
            log(f"ОШИБКА TIMEOUT: {error}")
            traceback.print_exc()

        except KeyboardInterrupt:
            log(
                "Скрипт остановлен пользователем. "
                "Сохраняем собранные данные..."
            )

        except Exception as error:
            log(f"КРИТИЧЕСКАЯ ОШИБКА: {error}")
            traceback.print_exc()

        finally:
            log("Финальное сохранение результатов...")

            try:
                save_results(results)
            except Exception as error:
                log(f"Не удалось сохранить CSV: {error}")
                traceback.print_exc()

            if context is not None:
                log("Закрываем контекст браузера...")

                try:
                    context.close()
                except Exception:
                    pass

            if browser is not None:
                log("Закрываем браузер...")

                try:
                    browser.close()
                except Exception:
                    pass

    log("=" * 60)
    log(f"Работа завершена. Найдено записей: {len(results)}")
    log(f"CSV-файл: {OUTPUT_FILE.resolve()}")
    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log(f"Необработанная ошибка: {error}")
        traceback.print_exc()