import { Component, OnInit } from '@angular/core';
import { Inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Component({
    selector: 'app-footer',
    templateUrl: './footer.component.html',
    styleUrls: ['./footer.component.scss']
})
export class FooterComponent implements OnInit {
    date = '';
    uptime = '';
    loadAverage = ''
    interval = null;

    constructor(
        private http: HttpClient,
        @Inject('ApiEndpoint') private readonly API_URL: string,
    ){}

    ngOnInit() {
        this.updateSysinfo();
        this.interval = setInterval(() => {
            this.updateSysinfo();
        }, 10000);
    }

    updateSysinfo() {
        this.http.jsonp(`${this.API_URL}/sysinfo`, 'callback')
            .subscribe(
                res => {
                    this.date = res['date'];
                    this.uptime = res['uptime'];
                    this.loadAverage = res['loadAverage'];
                },
                error => {
                    // ignore
                }
            );
        
    }

}
