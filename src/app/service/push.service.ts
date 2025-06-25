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
        this.connect();
    }

    private connect() {
        this.eventSource = new EventSource(`${this.API_URL}/event`);
        this.eventSource.addEventListener('message', (e: MessageEvent) => {
            this.notify(e.data);
        });
        this.eventSource.onerror = () => {
            if (this.eventSource.readyState == 2) {
                this.eventSource.close();
                setTimeout(() => this.connect(), 10000);
            }
        };
    }

    private notify(message: string) {
        this.dataSource.next(message);
    }
}
