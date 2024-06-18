from datetime import datetime
import logging
from pathlib import Path

from flask import abort
from flask import (
    render_template,
    request,
    Response,
    send_file,
)
from flask.views import MethodView
from flask_login import current_user
from werkzeug.utils import secure_filename

from forms.file_form import FileForm
from msu_aerosol.admin import get_complexes_dict
from msu_aerosol.config import allowed_extensions, upload_folder
from msu_aerosol.exceptions import FileExtensionError
from msu_aerosol.graph_funcs import choose_range, preprocessing_one_file
from msu_aerosol.graph_funcs import make_graph
from msu_aerosol.models import Complex, Device

__all__: list = []


def get_device_template(device_id: int, **kwargs) -> str:
    """
    Функция, возвращающая шаблон страницы прибора.
    Получает все необходимые переменные из kwargs и БД,
    передаём их в шаблон.

    :param device_id: Идентификатор прибора
    :param kwargs: Словарь с ключами 'message' и 'error'
    :return: Шаблон страницы прибора
    """

    message = kwargs.get('message')
    error = kwargs.get('error')
    form = kwargs.get('form')
    device_orm_obj = Device.query.get_or_404(device_id)
    complex_orm_obj = Complex.query.get_or_404(device_orm_obj.complex_id)
    complex_to_device = get_complexes_dict()
    device_to_name = {dev.name: dev.full_name for dev in Device.query.all()}
    min_date, max_date = choose_range(device_to_name[device_orm_obj.name])
    return render_template(
        'device/device.html',
        now=datetime.now(),
        view_name='device',
        device=device_orm_obj,
        complex=complex_orm_obj,
        complex_to_device=complex_to_device,
        user=current_user,
        device_to_name=device_to_name,
        min_date=str(min_date).replace(' ', 'T'),
        max_date=str(max_date).replace(' ', 'T'),
        message=message,
        error=error,
        form=form,
    )


class DevicePage(MethodView):
    """
    Представление страницы прибора.
    """

    def get(self, device_id: int) -> str:
        """
        Метод GET для страницы, только он доступен.

        :return: Шаблон страницы прибора
        """

        try:
            form = FileForm()
            return get_device_template(device_id, form=form)

        except IndexError:
            abort(404)


class DeviceDownload(MethodView):
    """
    Представление страницы скачивания файла прибора по выбранному диапазону.
    """

    def post(self, device_id: int) -> Response:
        """
        Метод POST для страницы, только он доступен.
        Получат все данные, введённые пользователет,
        отправляет ему файл с данными по выбранному диапазону.

        :param device_id: Идентификатор прибора
        :return: Файл с данными
        """

        data_range = (
            request.form.get('datetime_picker_start'),
            request.form.get('datetime_picker_end'),
        )
        full_name = Device.query.get(device_id).full_name
        buffer = make_graph(
            full_name,
            'download',
            begin_record_date=data_range[0],
            end_record_date=data_range[1],
        )
        logging.info(
            f'{current_user.login} downloaded '
            f'{full_name} data for '
            f'{[i.replace("T", " ") for i in data_range]} '
            f'period',
        )
        return send_file(
            buffer,
            as_attachment=True,
            attachment_filename=(
                f'{full_name}_{data_range[0]}-{data_range[1]}.csv'
            ),
            mimetype='text/csv',
        )


class DeviceUpload(MethodView):
    """
    Представление страницы отправки файла пользователем на сервер.
    """

    def post(self, device_id: int) -> str:
        """
        Метод POST для страницы, только он доступен.
        Пробует построить график для прибора с новым файлом,
        если не получается - сообщает об ошибке.

        :param device_id: Идентификатор прибора
        :return: Шаблон страницы прибора
        """

        form = FileForm()
        file = request.files['file']
        filename = secure_filename(file.filename)

        try:
            extension = filename.split('.')[-1]
            if extension not in allowed_extensions:
                raise FileExtensionError
            full_name = Device.query.get(device_id).full_name
            directory = f'{upload_folder}/{full_name}'
            if not Path(directory).exists():
                Path(directory).mkdir(parents=True)
            file.save(
                Path(directory, filename),
            )
            preprocessing_one_file(
                full_name,
                str(Path(directory) / filename),
                user_upload=True,
            )
            make_graph(full_name, 'full')
            make_graph(full_name, 'recent')
            return get_device_template(
                device_id,
                message='Файл успешно получен',
                form=form,
            )

        except (Exception, FileExtensionError):
            return get_device_template(
                device_id,
                error='Ошибка при загрузке файла',
                form=form,
            )
