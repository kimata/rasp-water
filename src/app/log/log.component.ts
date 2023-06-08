import { Subscription } from 'rxjs';

import { Component, OnInit, Pipe, PipeTransform } from '@angular/core';
import { Inject } from '@angular/core';
import { HttpClient, HttpParams  } from '@angular/common/http';

import { ToastService } from '../service/toast.service';

import * as moment from 'moment';
import 'moment/locale/ja';

import { PushService } from '../service/push.service';
import { NgbPagination } from '@ng-bootstrap/ng-bootstrap';
import { NgIf, NgFor, SlicePipe } from '@angular/common';

@Pipe({
    name: 'nl2br',
    standalone: true
})
export class NewlinePipe implements PipeTransform {
    transform(value: string): string {
        return value.replace(/\n/g, '<br />');
    }
}

export interface LogData {
    date: string;
    fromNow: string;
    message: string;
}
export interface LogResponse {
    data: LogData[];
}

@Component({
    selector: 'app-log',
    templateUrl: './log.component.html',
    styleUrls: ['./log.component.scss'],
    standalone: true,
    imports: [
        NgIf,
        NgFor,
        NgbPagination,
        SlicePipe,
        NewlinePipe,
    ],
})
export class LogComponent implements OnInit {
    private subscription: Subscription = Subscription.EMPTY;
    readonly pageSize = 10;
    page = 1;
    log: LogData[] = [];
    error = false;
    interval = 0;

    constructor(
        private http: HttpClient,
        private pushService: PushService,
        private toast: ToastService,
        @Inject('ApiEndpoint') private readonly API_URL: string,
    ){}

    ngOnInit() {
        this.updateLog();
        this.subscription = this.pushService.dataSource$.subscribe(
            msg => {
                if (msg == 'log') {
this.updateLog();
}
            }
        );
        this.interval = setInterval(() => {
            this.updateLog();
        }, 60000);

    }

    clear() {
        this.http.jsonp(`${this.API_URL}/log_clear`, 'callback')
            .subscribe(
                res => {
                    this.toast.show_sccess('正常にクリアできました。', {
                        title: '成功',
                    });
                },
                error => {
                }
            );
    }

    updateLog() {
        this.http.jsonp<LogResponse>(`${this.API_URL}/log_view`, 'callback')
            .subscribe(
                (res:LogResponse) => {
                    this.log = res['data'];
                    for(const entry in this.log) {
                        const date = moment(this.log[entry]['date']);
                        this.log[entry]['date'] = date.format('M月D日(ddd) HH:mm');
                        this.log[entry]['fromNow'] = date.fromNow();
                    }
                    this.error = false;
                },
                error => {
                    this.error = true;
                }
            );
    }
}
