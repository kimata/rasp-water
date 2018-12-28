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
        private toastrService: ToastrService,
        @Inject('ApiEndpoint') private readonly API_URL: string,
    ) { }

    private subscription;
    private state:any = [
        { 'enabled': false, 'time': '00:00', 'period': 0 },
        { 'enabled': false, 'time': '00:00', 'period': 0 },
    ];
    private savedState = null;
    private changed = false;
    private error = false;
    
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
        this.savedState = JSON.parse(JSON.stringify(this.state)); // NOTE: deep copy
        this.onChange();
    }
    
    updateSchedule(state=null) {
        let param = new HttpParams()
        if (state != null) {
            param = param.set('set', state);
        }
        this.http.jsonp(`${this.API_URL}/schedule_ctrl?${param.toString()}`, 'callback')
            .subscribe(
                res => {
                    if (this.savedState == null) {
                        this.savedState = JSON.parse(JSON.stringify(res)); // NOTE: deep copy
                        for (var stateItem of this.savedState) {
                            stateItem['time'] = moment(stateItem['time'], 'HH:mm');
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
            this.changed = (JSON.stringify(this.state) != JSON.stringify(this.savedState))
            console.log(JSON.stringify(this.state));
            console.log(JSON.stringify(this.savedState));
        }
    }
}
