from __future__ import absolute_import, unicode_literals
from celery import task
from django.conf import settings
import requests
import json
from .models import Setting
from django.core.mail import send_mail

headers = {'Authorization': settings.SMART_HOME_ACCESS_TOKEN}


def boiler_switcher(smoke_detector, cold_water, hot_water_target_temperature, boiler_temperature, state):
    # Проверка на дым и открытый кран холодной воды
    if smoke_detector or not cold_water:
        if state:
            return {'name': 'boiler', 'value': False}
        return

    rel = boiler_temperature / hot_water_target_temperature
    if (rel > 1.1 and state is True) or (rel < 0.9 and state is False):
        boiler_state = not state
        return {'name': 'boiler', 'value': boiler_state}


def air_conditioner_switcher(smoke_detector, bedroom_target_temp, bedroom_temp, state):
    # Проверка на дым
    if smoke_detector:
        if state:
            return {'name': 'air_conditioner', 'value': False}
        return

    rel = bedroom_temp / bedroom_target_temp
    if (rel > 1.1 and state is False) or (rel < 0.9 and state is True):
        conditioner_state = not state
        return {'name': 'air_conditioner', 'value': conditioner_state}


def curtains_switcher(outdoor_light, bedroom_light, curtains_state):
    if not curtains_state == "slightly_open":
        if (outdoor_light > 50 or bedroom_light) and curtains_state != 'close':
            return {'name': 'curtains', 'value': 'close'}

        elif outdoor_light < 50 and curtains_state != 'open' and not bedroom_light:
            return {'name': 'curtains', 'value': 'open'}


def emergent_light_switcher(smoke_detector, bedroom_light, bathroom_light):
    if smoke_detector:
        if bedroom_light or bathroom_light:
            return [{'name': 'bedroom_light', 'value': False}, {'name': 'bathroom_light', 'value': False}]


def emergency_washing_machine_switcher(cold_water, smoke_detector, washing_machine):
    if smoke_detector or not cold_water:
        if not washing_machine == 'off':
            return {'name': 'washing_machine', 'value': 'off'}


def emergency_water_switcher(leak_detector, cold_water, hot_water, data):
    if leak_detector:
        water = []
        if hot_water:
            data['hot_water'] = False
            water.append({'name': 'hot_water', 'value': False})

        if cold_water:
            data['cold_water'] = False
            water.append({'name': 'cold_water', 'value': False})

        send_mail('Leak',
                  'Leak detected.',
                  "from@example.com",
                  [settings.EMAIL_RECEPIENT], )

        return water


@task()
def smart_home_manager():
    # словарь для отправки post запроса:
    payload = {"controllers": []}

    # Получение данных с сервера дома:
    request = requests.get(settings.SMART_HOME_API_URL, headers=headers)
    sensors = request.json()['data']
    data = {dic['name']: dic['value'] for dic in sensors}

    # Управление кондиционером:
    bedroom_target_temp = Setting.objects.get(controller_name='bedroom_target_temperature').value
    bedroom_temp = data['bedroom_temperature']

    hot_water_temp = data['boiler_temperature']
    hot_water_target_temp = Setting.objects.get(controller_name='hot_water_target_temperature').value

    conditioner_state = data['air_conditioner']
    boiler_state = data['boiler']

    outdoor_light = int(data['outdoor_light'])

    # проверка протечек
    water_switcher = emergency_water_switcher(data['leak_detector'],
                                              data['cold_water'],
                                              data['hot_water'], data)

    air_conditioner = air_conditioner_switcher(data['smoke_detector'],
                                               bedroom_target_temp,
                                               bedroom_temp,
                                               conditioner_state)

    boiler = boiler_switcher(data['smoke_detector'],
                             data['cold_water'],
                             hot_water_target_temp,
                             hot_water_temp,
                             boiler_state)

    curtains = curtains_switcher(outdoor_light,
                                 data['bedroom_light'],
                                 data['curtains'])

    light_switcher = emergent_light_switcher(data['smoke_detector'],
                                             data['bathroom_light'],
                                             data['bedroom_light'])

    washing_machine = emergency_washing_machine_switcher(data['cold_water'],
                                                         data['smoke_detector'],
                                                         data['washing_machine'])


    # Вся информация добавляется в controllers если в переменных выше, есть хоть что то
    if air_conditioner is not None:
        payload['controllers'].append(air_conditioner)

    if boiler is not None:
        payload['controllers'].append(boiler)

    if curtains is not None:
        payload['controllers'].append(curtains)

    if light_switcher is not None:
        payload['controllers'] += light_switcher

    if washing_machine is not None:
        payload['controllers'].append(washing_machine)

    if water_switcher is not None:
        payload['controllers'] += water_switcher

    # Отправка запроса
    if payload['controllers'] != []:
        requests.post(settings.SMART_HOME_API_URL, headers=headers, data=json.dumps(payload))

    return data