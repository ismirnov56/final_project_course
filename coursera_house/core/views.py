from django.urls import reverse_lazy
from django.views.generic import FormView
from django.conf import settings
import requests
from django.http import HttpResponse
import json

from .models import Setting
from .form import ControllerForm


class ControllerView(FormView):
    form_class = ControllerForm
    template_name = 'core/control.html'
    success_url = reverse_lazy('form')
    headers = {'Authorization': settings.SMART_HOME_ACCESS_TOKEN}
    api_url = settings.SMART_HOME_API_URL
    data = {}

    def get(self, request):
        request = requests.get(self.api_url, headers=self.headers)
        if request.status_code == 200:
            detectors = request.json()['data']
            self.data = {dic['name']: dic['value'] for dic in detectors}
            return super(ControllerView, self).get(request)
        else:
            return HttpResponse(status='502')

    def post(self, request):
        request = requests.get(self.api_url, headers=self.headers)
        if request.status_code == 200:
            detectors = request.json()['data']
            self.data = {dic['name']: dic['value'] for dic in detectors}
            return super(ControllerView, self).post(request)
        else:
            return HttpResponse(status='502')

    def get_context_data(self, **kwargs):
        context = super(ControllerView, self).get_context_data()
        context['data'] = self.data
        return context

    def get_initial(self):
        return {
            'bedroom_target_temperature': Setting.objects.get(controller_name='bedroom_target_temperature').value,
            'hot_water_target_temperature': Setting.objects.get(controller_name='hot_water_target_temperature').value,
            'bedroom_light': self.data['bedroom_light'],
            'bathroom_light': self.data['bathroom_light'],
        }

    def form_valid(self, form):
        """
        Если форма валидна получаем данные от пользователя, сохраняем в БД (кондиционер и температуру воды),
        Отправляем на сервер дома для выполнения
        Состояние датчиков света, синхронизируется с сервером дома, не с локальной БД.
        """

        sensors = []

        # Если состояние выключателей света от пользователя отличается от состояний соответсвующих датчиков,
        # то меняем их на пользовательские, добавляем в список sensors.

        if form.cleaned_data['bedroom_light'] != self.data['bedroom_light']:
            sensors.append({"name": "bedroom_light", "value": form.cleaned_data['bedroom_light']})

        if form.cleaned_data['bathroom_light'] != self.data['bathroom_light']:
            sensors.append({"name": "bathroom_light", "value": form.cleaned_data['bathroom_light']})

        # Дополнительно проверяем датчик дыма. Если он сработал, свет никак не включится.
        if len(sensors) != 0 and not self.data['smoke_detector']:
            payload = {"controllers": sensors}
            post = requests.post(self.api_url, data=json.dumps(payload), headers=self.headers)
            if post.status_code != 200:
                return HttpResponse(status='502')

        # Сохраняем температуры в БД
        bedroom_temp = Setting.objects.get(controller_name='bedroom_target_temperature')
        bedroom_temp.value = form.cleaned_data['bedroom_target_temperature']
        bedroom_temp.save()

        hot_water_temp = Setting.objects.get(controller_name='hot_water_target_temperature')
        hot_water_temp.value = form.cleaned_data['hot_water_target_temperature']
        hot_water_temp.save()

        return super(ControllerView, self).form_valid(form)
