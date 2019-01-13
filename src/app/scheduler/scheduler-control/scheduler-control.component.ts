import { Component, OnInit } from '@angular/core';
import { Inject } from '@angular/core';
import { HttpClient, HttpParams  } from '@angular/common/http';

import { ToastrService } from 'ngx-toastr'; 

import * as moment from 'moment';

import { PushService } from '../../service/push.service';

@Component({
    selector: 'app-scheduler-control',
    templateUrl: './scheduler-control.component.html',
    styleUrls: ['./scheduler-control.component.scss'],
})

export class SchedulerControlComponent implements OnInit {
    constructor(
        private http: HttpClient,
        private pushService: PushService,
        public toastrService: ToastrService,
        @Inject('ApiEndpoint') private readonly API_URL: string,
    ) { }

    private subscription;
    private state:any = [
        {
            'is_active': true,
            'time': '00:00',
            'period': 0,
            'wday': [],
        },
        {
            'is_active': true,
            'time': '00:00',
            'period': 0,
            'wday': [],
        },
    ];
    private savedState = null;
    changed = false;
    error = false;
    
    ngOnInit() {
        this.updateSchedule();
        this.subscription = this.pushService.dataSource$.subscribe(
            msg => {
                if (msg == "schedule") this.updateSchedule();
            }
        );
    }

    save() {
        this.updateSchedule(this.state);
        this.savedState = this.state.map(x => Object.assign({}, x)); // NOTE: deep copy
        this.onChange();
    }
    
    updateSchedule(state=null) {
        let param = new HttpParams()
        if (state != null) {
            let sendState = state.map(x => Object.assign({}, x));
            for (let item of sendState) {
                item['time'] = this.convertTime(item['time'])
            }
            param = param.set('set', JSON.stringify(sendState));
        }
        this.http.jsonp(`${this.API_URL}/schedule_ctrl?${param.toString()}`, 'callback')
            .subscribe(
                res => {
                    if (this.savedState == null) {
                        this.savedState = JSON.parse(JSON.stringify(res)); // NOTE: deep copy
                        for (let item of this.savedState) {
                            item['time'] = this.convertTime(item['time']);
                        }
                    }
                    if (state != null) {
                        this.toastrService.success('正常に保存できました．', '成功');
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
            return time.format('HH:mm');
        } else {
            return moment(time, 'HH:mm').format('HH:mm');
        }
    }

    isStateDiffer(a, b) {
        for (let i = 0;  i < 2;  i++) {
            for (let key in a[i]) {
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
