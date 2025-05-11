import { Subscription } from 'rxjs';

import { Component, OnInit } from '@angular/core';
import { Inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';

import { PushService } from '../service/push.service';
import { FormsModule } from '@angular/forms';
import { NgIf, DecimalPipe, PercentPipe } from '@angular/common';

export interface ControlResponse {
    state: string;
    ctrl: string;
    remain: string;
}

export interface FlowResponse {
    flow: string;
}

@Component({
    selector: 'app-valve-control',
    templateUrl: './valve-control.component.html',
    styleUrls: ['./valve-control.component.scss'],
    imports: [NgIf, FormsModule, DecimalPipe, PercentPipe]
})
export class ValveControlComponent implements OnInit {
    private subscription: Subscription = Subscription.EMPTY;

    readonly FLOW_MAX = 12.0; // 表示する流量の最大値

    private interval = {
        ctrl: null,
        flow: 0,
        period: null,
    };
    private flowZeroCount = 0;
    loading = true;
    state = false;
    period = 1;
    remain = 0;
    flow = 0;
    error = {
        ctrl: false,
        flow: false,
    };

    constructor(
        private http: HttpClient,
        private pushService: PushService,
        @Inject('ApiEndpoint') private readonly API_URL: string
    ) {}

    ngOnInit() {
        this.updateCtrl(false);
        this.watchFlow();
        this.subscription = this.pushService.dataSource$.subscribe((msg) => {
            if (msg == 'control') {
                this.updateCtrl(false);
            }
        });
    }

    updatePeriod() {
        if (!this.state) {
            return;
        }
        this.updateCtrl(true, this.state);
    }

    updateCtrl(cmd: boolean, state = false) {
        // NOTE: state が true の場合は制御
        let param = new HttpParams();
        if (cmd) {
            param = param.set('cmd', '1');
            param = param.set('state', state ? 1 : 0);
            param = param.set('period', String(this.period * 60));
        }
        this.http
            .jsonp<ControlResponse>(`${this.API_URL}/valve_ctrl?${param.toString()}`, 'callback')
            .subscribe(
                (res: ControlResponse) => {
                    if (res['state'] == '1') {
                        this.watchFlow();
                    }
                    this.state = res['state'] == '1';
                    this.remain = Number(res['remain']);
                    this.error['ctrl'] = false;
                    this.loading = false;
                },
                (error) => {
                    this.error['ctrl'] = true;
                    this.loading = false;
                }
            );
    }

    watchFlow() {
        if (this.interval['flow'] != 0) {
            return;
        }
        this.interval['flow'] = window.setInterval(() => {
            this.updateCtrl(false);
            this.updateFlow();
        }, 500);
    }

    unwatchFlow() {
        clearInterval(this.interval['flow']);
        this.interval['flow'] = 0;
    }

    updateFlow() {
        this.http.jsonp<FlowResponse>(`${this.API_URL}/valve_flow`, 'callback').subscribe(
            (res: FlowResponse) => {
                this.flow = Math.min(Number(res['flow']), this.FLOW_MAX);
                this.error['flow'] = false;
                if (this.flow < 0.03) {
                    this.flowZeroCount++;
                } else {
                    this.flowZeroCount = 0;
                }

                // NOTE: バルブを閉じてから、流量が 0 になって落ち着いたら、
                // 流量バーの更新を停止する．
                if (this.flowZeroCount == 10 && !this.state) {
                    this.unwatchFlow();
                }
            },
            (error) => {
                this.error['flow'] = true;
            }
        );
    }
}
