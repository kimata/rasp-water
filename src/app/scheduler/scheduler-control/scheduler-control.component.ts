import { Component, OnInit } from '@angular/core';
import { Inject } from '@angular/core';
import { HttpClient, HttpParams  } from '@angular/common/http';

import { ToastService } from '../../service/toast.service';

import * as moment from 'moment';

import { PushService } from '../../service/push.service';
import { SchedulerEntryComponent } from '../scheduler-entry/scheduler-entry.component';
import { NgIf } from '@angular/common';

@Component({
    selector: 'app-scheduler-control',
    templateUrl: './scheduler-control.component.html',
    styleUrls: ['./scheduler-control.component.scss'],
    standalone: true,
    imports: [NgIf, SchedulerEntryComponent],
})

export class SchedulerControlComponent implements OnInit {
    constructor(
        private http: HttpClient,
        private pushService: PushService,
        public toast: ToastService,
        @Inject('ApiEndpoint') private readonly API_URL: string,
    ) { }

    private subscription;
    private state: any = [
        {
            is_active: true,
            time: '00:00',
            period: 0,
            wday: [],
        },
        {
            is_active: true,
            time: '00:00',
            period: 0,
            wday: [],
        },
    ];
    private savedState = null;
    changed = false;
    error = false;

    ngOnInit() {
        this.updateSchedule();
        this.subscription = this.pushService.dataSource$.subscribe(
            msg => {
                if (msg == 'schedule') {
this.updateSchedule();
}
            }
        );
    }

    save() {
        this.updateSchedule(this.state);
        this.savedState = this.state.map(x => Object.assign({}, x)); // NOTE: deep copy
        this.onChange();
    }

    updateSchedule(state=null) {
        let param = new HttpParams();
        if (state != null) {
            const sendState = state.map(x => Object.assign({}, x));
            for (const item of sendState) {
                item['time'] = this.convertTime(item['time']);
            }
            param = param.set('set', JSON.stringify(sendState));
        }
        this.http.jsonp(`${this.API_URL}/schedule_ctrl?${param.toString()}`, 'callback')
            .subscribe(
                res => {
                    if (this.savedState == null) {
                        this.savedState = JSON.parse(JSON.stringify(res)); // NOTE: deep copy
                        for (const item of this.savedState) {
                            item['time'] = this.convertTime(item['time']);
                        }
                    }
                    if (state != null) {
                        this.toast.show_sccess('正常に保存できました。', {
                            title: '成功',
                        });
                    }
                    this.state = res;
                    this.error = false;
                },
                error => {
                    this.error = true;
                }
            );
    }

    onChange() {
        if (this.savedState != null) {
            this.changed = this.isStateDiffer(this.state, this.savedState);
        }
    }

    convertTime(time) {
        if (time instanceof moment) {
            return (time as moment.Moment).format('HH:mm');
        } else {
            return moment(time, 'HH:mm').format('HH:mm');
        }
    }

    isStateDiffer(a, b) {
        for (let i = 0;  i < 2;  i++) {
            for (const key in a[i]) {
                if (key == 'time') {
                    if (this.convertTime(a[i][key]) != this.convertTime(b[i][key])) {
                        return true;
                    }
                } else {
                    if (JSON.stringify(a[i][key]) != JSON.stringify(b[i][key])) {
                        return true;
                    }
                }
            }
        }
        return false;
    }
}
