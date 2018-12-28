import { Subscription } from 'rxjs';

import { Component, OnInit } from '@angular/core';
import { Inject } from '@angular/core';
import { HttpClient, HttpParams  } from '@angular/common/http';

import * as moment from 'moment'; 
import 'moment/locale/ja'

import { PushService } from '../service/push.service';

@Component({
    selector: 'app-log',
    templateUrl: './log.component.html',
    styleUrls: ['./log.component.scss']
})
export class LogComponent implements OnInit {
    private subscription;
    readonly pageSize = 10;
    readonly page = 1;
    private log = []
    private error = false;

    constructor(
        private http: HttpClient,
        private pushService: PushService,
        @Inject('ApiEndpoint') private readonly API_URL: string,
    ){}

    ngOnInit() {
        this.updateLog();
        this.subscription = this.pushService.dataSource$.subscribe(
            msg => {
                if (msg == "log") this.updateLog();
            }
        );
    }
    
    updateLog() {
        this.http.jsonp(`${this.API_URL}/log`, 'callback')
            .subscribe(
                res => {
                    this.log = res['data'];
                    for(let entry in this.log) {
                        this.log[entry]['fromNow'] = moment(this.log[entry]['date']).fromNow();
                    }
                    this.error = false;
                },
                error => {
                    this.error = true;
                }
            );
    }
}
