import re
import time
import random
import sqlite3
import smtplib
import requests
from models import Offer
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from settings import (
    BASE_URL, OFFERS_URL, LOCATION_TAG_CLASS, PRICE_TAG_CLASS, SMTP_HOST,
    DETAILS_TAG_CLASS, SMTP_PORT, SENDER, SENDER_PASSWORD, RECEIVERS
)


def get_offers():
    response = requests.get(OFFERS_URL)
    if 200 <= response.status_code <= 299:
        page = BeautifulSoup(response.text, 'html.parser')
    else:
        return None

    offers_tag = None
    for tag in page.find_all('div', attrs={'data-cy': True}):
        if tag['data-cy'] == 'frontend.search.listing':
            offers_tag = tag

    offers = []
    if offers_tag is None:
        return None

    for offer in offers_tag.find_all('li'):
        title_tag = offer.find_next('h3', attrs={'title': True})
        location_tag = offer.find_next(
            'span', attrs={'class': LOCATION_TAG_CLASS}
        )
        price_tag = offer.find_next(
            'p', attrs={'class': PRICE_TAG_CLASS}
        )
        details_tag = offer.find_next(
            'p', attrs={'class': DETAILS_TAG_CLASS}
        )
        link_tag = offer.find_next(
            'a', attrs={'data-cy': 'listing-item-link', 'href': True}
        )
        details_numbers = re.findall(r'\d+', details_tag.get_text())

        title = title_tag.get_text()
        location = location_tag.get_text()
        price = float(price_tag.get_text().split('\xa0')[0])
        link = urljoin(BASE_URL, link_tag['href'])
        rooms = int(details_numbers[0])
        area = float(details_numbers[1])

        offers.append(Offer(title, location, price, rooms, area, link))

    return offers


def create_table(db_conn, table, keys, types):
    cursor = db_conn.cursor()
    keys_types = ','.join([f'{key} {type}' for key, type in zip(keys, types)])
    cursor.execute(f'CREATE TABLE IF NOT EXISTS {table} ({keys_types})')
    db_conn.commit()


def inset_values(db_conn, table, values):
    cursor = db_conn.cursor()
    value_tags = ','.join(['?'] * len(values))
    cursor.execute(f'INSERT INTO {table} VALUES ({value_tags})', values)
    db_conn.commit()


def offer_exists(db_conn, offer):
    cursor = db_conn.cursor()
    cursor.execute(f'''\
        SELECT EXISTS(SELECT 1 FROM offers WHERE title="{offer.title}")''')
    return cursor.fetchone()[0] == 1


def connect_SMTP(host, port):
    server = smtplib.SMTP(host, port)
    server.starttls()
    try:
        server.login(SENDER, SENDER_PASSWORD)
    except smtplib.SMTPAuthenticationError:
        print("Unable to sign in")
    except Exception as e:
        print(e)

    return server


def send_offers(smtp_server, offers):
    for receiver in RECEIVERS:
        message = f"From: {SENDER}\nTo: {receiver}\nSubject: New offers\n"
        for offer in offers:
            message += f'\n{str(offer)}\n{"="*40}'

        try:
            smtp_server.sendmail(SENDER, receiver, message.encode('utf-8'))
            print(f'Email with {len(offers)} new offers to {receiver} has been sent!')  # noqa: E501
        except Exception as e:
            print(f'Unable to send email to {receiver}', e)


def main():
    db_conn = sqlite3.connect('offers.db')
    create_table(
        db_conn, 'offers',
        keys=[
            'add_date', 'title', 'location', 'price', 'rooms', 'area', 'link'
        ],
        types=[
            'TEXT', 'TEXT', 'TEXT', 'REAL', 'INTEGER', 'REAL', 'TEXT'
        ]
    )

    smtp_server = connect_SMTP(host=SMTP_HOST, port=SMTP_PORT)

    while 1:
        try:
            offers = get_offers()
            new_offers = []
            for offer in offers:
                if not offer_exists(db_conn, offer):
                    new_offers.append(offer)
                    inset_values(db_conn, 'offers', (
                        datetime.now(), offer.title, offer.location,
                        offer.price, offer.rooms, offer.area, offer.link
                        )
                    )

            if new_offers:
                send_offers(smtp_server, offers)
            else:
                print(f'No new offers found... ({datetime.now()})')

            time.sleep(random.randint(840, 960))  # sleep for 15min +-1min
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(e)

        break


if __name__ == "__main__":
    main()
