import { Component, OnInit } from '@angular/core';
import { Inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import build from '../../build';

import 'dayjs/locale/ja';
import dayjs, { locale, extend } from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
locale('ja');
extend(relativeTime);

export interface SysinfoResponse {
    date: string;
    uptime: string;
    loadAverage: string;
}

@Component({
    selector: 'app-footer',
    templateUrl: './footer.component.html',
    styleUrls: ['./footer.component.scss'],
    standalone: true,
})
export class FooterComponent implements OnInit {
    buildDate = dayjs(build.timestamp).format('llll');
    buildDateFrom = dayjs(build.timestamp).fromNow();
    date = '';
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

                if (response.data['image_build_date'] !== '') {
                    const imageBuildDate = moment(response.data['image_build_date']);
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
                this.loadAverage = res['loadAverage'];
            },
            (error) => {
                // ignore
            }
        );
    }
}
