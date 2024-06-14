from datetime import timedelta
from io import BytesIO
import os
from pathlib import Path

from hsluv import hsluv_to_rgb
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.offline as offline
from yadisk import YaDisk

from msu_aerosol.config import yadisk_token
from msu_aerosol.exceptions import ColumnsMatchError, TimeFormatError
from msu_aerosol.models import Device, DeviceTimeColumn

__all__ = []


def get_device_by_name(name: str, app=None) -> Device | None:
    if app:
        with app.app_context():
            return Device.query.filter_by(full_name=name).first()

    return Device.query.filter_by(full_name=name).first()


main_path = 'data'
disk = YaDisk(token=yadisk_token)
base_url = 'https://cloud-api.yandex.net/v1/disk/public/resources/download?'


def make_format_date(date: str) -> str:
    return ''.join(['%' + i if i.isalpha() else i for i in list(date)])


def make_visible_date_format(date: str) -> str:
    return date.replace('%', '')


def no_csv(link: str) -> bool:
    return all(
        not i['name'].endswith('.csv')
        for i in disk.get_public_meta(link, limit=1000)['embedded']['items']
    )


def download_last_modified_file(links: list[str], app=None) -> None:
    list_data_path = []
    for link in links:
        if app:
            with app.app_context():
                full_name = Device.query.filter_by(link=link).first().full_name
        else:
            full_name = Device.query.filter_by(link=link).first().full_name
        last_modified_file = sorted(
            filter(
                lambda y: y['name'].endswith(
                    '.txt' if no_csv(link) else '.csv',
                ),
                disk.get_public_meta(link, limit=1000)['embedded']['items'],
            ),
            key=lambda x: x['modified'],
        )[-1]
        file_path = f'data/{full_name}/{last_modified_file["name"]}'
        disk.download_by_link(
            last_modified_file['file'],
            f'{main_path}/{full_name}/{last_modified_file["name"]}',
        )
        list_data_path.append([full_name, file_path])
    for i in list_data_path:
        if app:
            with app.app_context():
                dev = Device.query.filter_by(full_name=i[0]).first()
        else:
            dev = Device.query.filter_by(full_name=i[0]).first()
        if not dev.archived:
            try:
                preprocessing_one_file(i[0], i[1], app=app)
                make_graph(i[0], spec_act='full', app=app)
                make_graph(i[0], spec_act='recent', app=app)

            except (KeyError, Exception):
                pass


def download_device_data(link: str) -> None:
    items = disk.get_public_meta(link, limit=1000)
    full_name = Device.query.filter_by(link=link).first().full_name
    for i in items['embedded']['items']:
        if not Path(f'{main_path}/{full_name}').exists():
            Path(f'{main_path}/{full_name}').mkdir(parents=True)
        if i['name'].endswith('.csv') or (
            i['name'].endswith('.txt') and no_csv(link)
        ):
            disk.download_by_link(
                i['file'],
                f'{main_path}/{full_name}/{i["name"]}',
            )


def preprocess_device_data(name_folder: str) -> None:
    for name_file in os.listdir(f'{main_path}/{name_folder}'):
        preprocessing_one_file(
            name_folder,
            f'{main_path}/{name_folder}/{name_file}',
        )


def get_time_col(device_obj):
    return (
        DeviceTimeColumn.query.filter_by(
            use=True,
            device_id=device_obj.id,
        )
        .first()
        .name
    )


def get_columns(device_obj):
    return Device.query.filter_by(id=device_obj.id).first().columns


def proc_spaces(df, time_col):
    df = df.sort_values(by=time_col)
    diff_mode = df[time_col].diff().mode().values[0] * 1.1
    new_rows = []
    for i in range(len(df) - 1):
        diff = df.loc[i + 1, time_col] - df.loc[i, time_col]
        if diff > diff_mode:
            new_date1 = df.loc[i, time_col] + pd.Timedelta(seconds=1)
            new_date2 = df.loc[i + 1, time_col] - pd.Timedelta(seconds=1)
            new_row1 = {time_col: new_date1}
            new_row2 = {time_col: new_date2}
            new_rows.extend([new_row1, new_row2])
    return pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)


def preprocessing_one_file(
    device: str,
    path: str,
    user_upload=False,
    app=None,
) -> None:
    if path.endswith('.csv'):
        df = pd.read_csv(
            path,
            sep=None,
            engine='python',
            decimal=',',
            on_bad_lines='skip',
        )
    else:
        df = pd.read_csv(
            path,
            sep='\t',
            encoding='latin',
            decimal=',',
            on_bad_lines='skip',
        )
    if df.shape[0] == 0:
        return
    device_obj = get_device_by_name(device, app=app)
    if app:
        with app.app_context():
            time_col = get_time_col(device_obj)
    else:
        time_col = get_time_col(device_obj)
    columns = [j.name for j in device_obj.columns if j.use]
    if any(
        (i not in list(df.columns) for i in [time_col] + columns),
    ):
        raise ColumnsMatchError('Проблемы с совпадением столбцов')
    df = df[[time_col] + columns]
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    if not Path(f'proc_data/{device}').exists():
        Path(f'proc_data/{device}').mkdir(parents=True)
    try:
        if time_col == 'timestamp':
            df[time_col] = pd.to_datetime(df[time_col], unit='s')
        else:
            df[time_col] = pd.to_datetime(
                df[time_col],
                format=make_format_date(device_obj.time_format),
            )
    except (TypeError, ValueError):
        if not app:
            raise TimeFormatError('Проблемы с форматом времени')
        return
    df = proc_spaces(df, time_col)
    for year in df[time_col].dt.year.unique():
        for month in df[time_col].dt.month.unique():
            df_month = df.loc[
                (
                    (df[time_col].dt.month == month)
                    & (df[time_col].dt.year == year)
                )
            ]
            month = '0' + str(month) if month < 10 else str(month)
            file_path = f'proc_data/{device}/{year}_{month}.csv'
            if Path(file_path).exists() or user_upload:
                df_help = pd.read_csv(file_path)
                df_help[time_col] = pd.to_datetime(df_help[time_col])
                df_month = pd.concat(
                    [df_help, df_month],
                    ignore_index=True,
                )
                df_month.drop_duplicates()
            if len(df_month) == 0:
                continue
            df_month = df_month.sort_values(by=time_col).drop_duplicates(
                subset=[time_col]
            )
            df_month.to_csv(file_path, index=False)


def choose_range(device: str, app=None) -> tuple[pd.Timestamp, pd.Timestamp]:
    time_col = [
        i.name
        for i in get_device_by_name(device, app=app).time_columns
        if i.use
    ][0]
    list_files = os.listdir(f'proc_data/{device}')
    proc_data = f'proc_data/{device}/{max(list_files)}'
    max_date = pd.to_datetime(
        pd.read_csv(proc_data)[time_col].iloc[-1],
    )
    min_date = max_date - timedelta(days=14)
    return min_date, max_date


def get_spaced_colors(n: int) -> list:
    color_h = np.random.uniform(low=0, high=360, size=(1, n))
    color_l = np.random.normal(loc=66, scale=10, size=(1, n))
    color_s = np.random.uniform(low=80, high=100, size=(1, n))

    image = np.dstack((color_h, color_s, color_l))
    image = np.apply_along_axis(hsluv_to_rgb, 2, image)
    return [
        '#{:02x}{:02x}{:02x}'.format(
            int(rgb[0] * 255),
            int(rgb[1] * 255),
            int(rgb[2] * 255),
        )
        for rgb in image[0]
    ]


def make_graph(
    device: str,
    spec_act: str,
    begin_record_date=None,
    end_record_date=None,
    app=None,
) -> None | BytesIO:
    if spec_act == 'download':
        begin_record_date = pd.to_datetime(
            begin_record_date,
            format=(
                '%Y-%m-%dT%H:%M'
                if pd.to_datetime(begin_record_date).second == 0
                else '%Y-%m-%dT%H:%M:%S'
            ),
        )
        end_record_date = pd.to_datetime(
            end_record_date,
            format=(
                '%Y-%m-%dT%H:%M'
                if pd.to_datetime(end_record_date).second == 0
                else '%Y-%m-%dT%H:%M:%S'
            ),
        )
    device_obj = get_device_by_name(device, app=app)
    time_col = list(filter(lambda x: x.use, device_obj.time_columns))[0].name
    if not begin_record_date or not end_record_date:
        begin_record_date, end_record_date = choose_range(device, app=app)
    if spec_act == 'full':
        begin_record_date = end_record_date - timedelta(days=14)
    if spec_act == 'recent':
        begin_record_date = end_record_date - timedelta(days=3)
    current_date, combined_data = begin_record_date, pd.DataFrame()
    while current_date <= end_record_date + timedelta(days=100):
        try:
            data = pd.read_csv(
                f'proc_data/'
                f'{device}/'
                f'{current_date.strftime("%Y_%m")}.csv',
            )
            combined_data = pd.concat([combined_data, data], ignore_index=True)
            current_date += timedelta(days=29)
        except FileNotFoundError:
            current_date += timedelta(days=29)
    combined_data[time_col] = pd.to_datetime(combined_data[time_col])
    combined_data = proc_spaces(combined_data, time_col)
    m = max(combined_data[time_col])
    last_48_hours = [m - timedelta(days=2), m]
    last_2_weeks = [m - timedelta(days=14), m]
    if spec_act == 'recent':
        combined_data = combined_data.loc[
            (last_48_hours[0] <= pd.to_datetime(combined_data[time_col]))
            & (pd.to_datetime(combined_data[time_col]) <= last_48_hours[1])
        ]
    if spec_act == 'full':
        combined_data = combined_data.loc[
            (last_2_weeks[0] <= pd.to_datetime(combined_data[time_col]))
            & (pd.to_datetime(combined_data[time_col]) <= last_2_weeks[1])
        ]
    combined_data.set_index(time_col, inplace=True)
    combined_data = combined_data.replace(
        ',',
        '.',
        regex=True,
    ).astype(float)
    if spec_act == 'download':
        buffer = BytesIO()
        combined_data.reset_index(inplace=True)
        combined_data = combined_data.loc[
            (begin_record_date <= pd.to_datetime(combined_data[time_col]))
            & (pd.to_datetime(combined_data[time_col]) <= end_record_date)
        ]
        combined_data.to_csv(buffer, index=False)
        buffer.seek(0)
        return buffer

    if spec_act == 'recent':
        q1, q3 = combined_data.quantile(0.1), combined_data.quantile(0.9)
        iqr = combined_data.quantile(0.9) - combined_data.quantile(0.1)
        lower_bound, upper_bound = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        filtered_df = combined_data[
            (
                (combined_data >= lower_bound) & (combined_data <= upper_bound)
            ).all(axis=1)
        ]
        std = filtered_df.std()
        mask = (combined_data.diff().abs().div(std) <= 1).all(axis=1)
        consecutive_true = mask & mask.shift(1, fill_value=False)
        mask[(consecutive_true.cumsum() % 2 == 0) & consecutive_true] = False
        combined_data.loc[mask, :] = (
            combined_data.loc[mask, :].values
            + combined_data.loc[mask.shift(-1, fill_value=False), :].values
        ) / 2
        mask_shifted = mask.shift(-1, fill_value=False)
        combined_data = combined_data[~mask_shifted]
    combined_data.reset_index(inplace=True)
    combined_data = combined_data.sort_values(by=time_col)
    fig = px.line(
        combined_data,
        x=time_col,
        y=[i.name for i in device_obj.columns if i.use],
    )
    if app:
        with app.app_context():
            cols = get_columns(device_obj)
    else:
        cols = get_columns(device_obj)
    for trace in fig.data:
        for i in cols:
            if i.name == trace['name']:
                trace.visible = True if i.default else 'legendonly'
                break

    fig.update_layout(
        title=str(device),
        xaxis={'title': [i.name for i in device_obj.time_columns if i.use][0]},
        plot_bgcolor='white',
        paper_bgcolor='white',
        showlegend=True,
    )
    fig.update_traces(line={'width': 2})
    fig.update_xaxes(
        gridcolor='grey',
        showline=True,
        linewidth=1,
        linecolor='black',
        mirror=True,
        tickformat='%H:%M\n%d.%m.%Y',
        minor_griddash='dot',
    )
    fig.update_yaxes(
        gridcolor='grey',
        showline=True,
        linewidth=1,
        linecolor='black',
        mirror=True,
    )
    offline.plot(
        fig,
        filename=(
            f'templates/'
            f'includes/'
            f'devices/'
            f'{spec_act}'
            f'/graph_{device}.html'
        ),
        auto_open=False,
        include_plotlyjs=False,
    )

    return None
