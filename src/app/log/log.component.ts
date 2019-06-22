import { Subscription } from 'rxjs';

import { Component, OnInit, Pipe, PipeTransform } from '@angular/core';
import { Inject } from '@angular/core';
import { HttpClient, HttpParams  } from '@angular/common/http';

import { ToastrService } from 'ngx-toastr';

import * as moment from 'moment'; 
import 'moment/locale/ja'

import { PushService } from '../service/push.service';

@Pipe({ name: 'nl2br' })
export class NewlinePipe implements PipeTransform {
    transform(value: string): string {
        return value.replace(/\n/g, '<br />');
    }
}

@Component({
    selector: 'app-log',
    templateUrl: './log.component.html',
    styleUrls: ['./log.component.scss'],
})
export class LogComponent implements OnInit {
    private subscription;
    readonly pageSize = 10;
    readonly page = 1;
    private log = []
    error = false;
    interval = null;

    constructor(
        private http: HttpClient,
        private pushService: PushService,
        public toastrService: ToastrService,
        @Inject('ApiEndpoint') private readonly API_URL: string,
    ){}

    ngOnInit() {
        this.updateLog();
        this.subscription = this.pushService.dataSource$.subscribe(
            msg => {
                if (msg == "log") this.updateLog();
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
                    this.toastrService.success('正常にクリアできました．', '成功');
                },
                error => {
                }
            );
    }
    
    updateLog() {
        this.http.jsonp(`${this.API_URL}/log_view`, 'callback')
            .subscribe(
                res => {
                    this.log = res['data'];
                    for(let entry in this.log) {
                        let date = moment(this.log[entry]['date']);
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
