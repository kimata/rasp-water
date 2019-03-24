import { Subscription } from 'rxjs';

import { Component, OnInit } from '@angular/core';
import { Inject } from '@angular/core';
import { HttpClient, HttpParams  } from '@angular/common/http';

import { PushService } from '../service/push.service';

@Component({
    selector: 'app-valve-control',
    templateUrl: './valve-control.component.html',
    styleUrls: ['./valve-control.component.scss']
})

export class ValveControlComponent implements OnInit {
    private subscription;
    
    private readonly FLOW_MAX = 12.0 // 流量系の最大値
    private interval = {
        'ctrl': null,
        'flow': null,
        'period': null
    };
    loading = true;
    private state = false;
    private period = 0;
    private flow = 0;
    private flowZeroCount = 0;
    error = {
        'ctrl': false,
        'flow': false,
    };
    
    constructor(
        private http: HttpClient,
        private pushService: PushService,
        @Inject('ApiEndpoint') private readonly API_URL: string,
    ){}

    ngOnInit() {
        this.updateCtrl();
        this.watchFlow();
        this.subscription = this.pushService.dataSource$.subscribe(
            msg => {
                if (msg != "schedule") this.updateCtrl();
            }
        );
    }

    updateCtrl(state=null) {
        let param = new HttpParams()
        if (state != null) {
            param = param.set('set', state ? '1' : '0');
            param = param.set('period', String(this.period));
        }
        this.http.jsonp(`${this.API_URL}/valve_ctrl?${param.toString()}`, 'callback')
            .subscribe(
                res => {
                    if (res['state'] =="1") this.watchFlow();
                    this.state = (res['state'] =="1");
                    this.period = Number(res['period']);
                    this.error['ctrl'] = false;
                    this.loading = false;
                },
                error => {
                    this.error['ctrl'] = true;
                    this.loading = false;     
                }
            );
    }

    watchFlow() {
        if (this.interval['flow'] != null) return;
        this.interval['flow'] = setInterval(() => {
            this.updateFlow();
        }, 500);
    }

    unwatchFlow() {
        clearInterval(this.interval['flow']);
        this.interval['flow'] = null;
    }
    
    updateFlow() {
        this.http.jsonp(`${this.API_URL}/valve_flow`, 'callback')
            .subscribe(
                res => {
                    this.flow = Math.min(Number(res['flow']), this.FLOW_MAX);
                    this.error['flow'] = false;
                    if (Math.round(this.flow) == 0) {
                        this.flowZeroCount++;
                    } else {
                        this.flowZeroCount = 0;
                    }
                    if ((this.flowZeroCount == 10) && !this.state) {
                        this.unwatchFlow();
                    }
                },
                error => {
                    this.error['flow'] = true;
                }
            );
        
    }
}
