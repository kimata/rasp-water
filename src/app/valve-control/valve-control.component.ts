import { Subscription } from 'rxjs';

import { Component, OnInit } from '@angular/core';
import { Inject } from '@angular/core';
import { HttpClient, HttpParams  } from '@angular/common/http';

import { PushService } from '../service/push.service';
import { FormsModule } from '@angular/forms';
import { NgIf, DecimalPipe, PercentPipe } from '@angular/common';

export interface ControlResponse {
    state: string;
    ctrl: string;
    period: string;
}

export interface FlowResponse {
    flow: string;
}


@Component({
    selector: 'app-valve-control',
    templateUrl: './valve-control.component.html',
    styleUrls: ['./valve-control.component.scss'],
    standalone: true,
    imports: [NgIf, FormsModule, DecimalPipe, PercentPipe]
})
export class ValveControlComponent implements OnInit {
    private subscription: Subscription = Subscription.EMPTY;

    readonly FLOW_MAX = 12.0; // 表示する流量の最大値
    private interval = {
        ctrl: null,
        flow: 0,
        period: null
    };
    private flowZeroCount = 0;
    loading = true;
    state = false;
    period = 0;
    flow = 0;
    error = {
        ctrl: false,
        flow: false,
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
                if (msg != 'schedule') {
this.updateCtrl();
}
            }
        );
    }

    updatePeriod() {
        if (!this.state) {
return;
}
        if (this.period == 0) {
this.period = 1;
}
        this.updateCtrl(true);
    }

    updateCtrl(state=false) {
        let param = new HttpParams();
        if (state) {
            param = param.set('set', state ? '1' : '0');
            param = param.set('period', String(this.period));
        }
        this.http.jsonp<ControlResponse>(`${this.API_URL}/valve_ctrl?${param.toString()}`, 'callback')
            .subscribe(
                (res: ControlResponse) => {
                    if (res['state'] =='1') {
this.watchFlow();
}
                    this.state = (res['state'] =='1');
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
        if (this.interval['flow'] != null) {
return;
}
        this.interval['flow'] = setInterval(() => {
            this.updateFlow();
        }, 500);
    }

    unwatchFlow() {
        clearInterval(this.interval['flow']);
        this.interval['flow'] = 0;
    }

    updateFlow() {
        this.http.jsonp<FlowResponse>(`${this.API_URL}/valve_flow`, 'callback')
            .subscribe(
                (res:FlowResponse) => {
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
