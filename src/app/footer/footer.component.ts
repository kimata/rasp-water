import { Component, OnInit } from '@angular/core';
import { Inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import build from '../../build';

import 'dayjs/locale/ja';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import localizedFormat from 'dayjs/plugin/localizedFormat';
dayjs.locale('ja');
dayjs.extend(relativeTime);
dayjs.extend(localizedFormat);

export interface SysinfoResponse {
    image_build_date: string;
    date: string;
    timezone: string;
    uptime: string;
    load_average: string;
}

@Component({
    selector: 'app-footer',
    templateUrl: './footer.component.html',
    styleUrls: ['./footer.component.scss'],
    standalone: true,
})
export class FooterComponent implements OnInit {
    imageBuildDate = '';
    imageBuildDateFrom = '';
    buildDate = dayjs(build.timestamp).format('llll');
    buildDateFrom = dayjs(build.timestamp).fromNow();
    date = '';
    timezone = '';
    uptime = '';
    uptimeFrom = '';
    loadAverage = '';
    interval = 0;

    constructor(private http: HttpClient, @Inject('ApiEndpoint') private readonly API_URL: string) {}

    ngOnInit() {
        this.updateSysinfo();
        this.interval = window.setInterval(() => {
            this.updateSysinfo();
        }, 60000);
    }

    updateSysinfo() {
        this.http.jsonp<SysinfoResponse>(`${this.API_URL}/sysinfo`, 'callback').subscribe(
            (res: SysinfoResponse) => {
                const date = dayjs(res['date']);
                const uptime = dayjs(res['uptime']);

                if (res['image_build_date'] !== '') {
                    const imageBuildDate = dayjs(res['image_build_date']);
                    this.imageBuildDate = imageBuildDate.format('llll');
                    this.imageBuildDateFrom = imageBuildDate.fromNow();
                } else {
                    this.imageBuildDate = '?';
                    this.imageBuildDateFrom = '?';
                }

                this.date = date.format('llll');
                this.timezone = res['timezone'];
                this.uptime = uptime.format('llll');
                this.uptimeFrom = uptime.fromNow();
                this.loadAverage = res['load_average'];
            },
            (error) => {
                // ignore
            }
        );
    }
}
