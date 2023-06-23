import { Subject } from 'rxjs';

import { Injectable } from '@angular/core';
import { Inject } from '@angular/core';

@Injectable({
    providedIn: 'root',
})
export class PushService {
    private dataSource = new Subject<string>();
    public dataSource$ = this.dataSource.asObservable();
    private eventSource: any = null;

    constructor(@Inject('ApiEndpoint') private readonly API_URL: string) {
        const self = this;
        this.connect();
    }

    private connect() {
        const self = this;
        this.eventSource = new EventSource(`${this.API_URL}/event`);
        this.eventSource.addEventListener('message', function (e: MessageEvent) {
            self.notify(e.data);
        });
        this.eventSource.onerror = function () {
            if (self.eventSource.readyState == 2) {
                self.eventSource.close();
                setTimeout(self.connect, 10000);
            }
        };
    }

    private notify(message: string) {
        this.dataSource.next(message);
    }
}
