import { Subject } from 'rxjs';

import { Injectable } from '@angular/core';
import { Inject } from '@angular/core';

@Injectable({
    providedIn: 'root',
})
export class PushService {
    private dataSource = new Subject<string>();
    public dataSource$ = this.dataSource.asObservable();
    private eventSource;

    constructor(@Inject('ApiEndpoint') private readonly API_URL: string) {
        const self = this;
        this.eventSource = new EventSource(`${this.API_URL}/event`);
        this.eventSource.addEventListener('message', function (e) {
            self.notify(e.data);
        });
    }

    private notify(message: string) {
        this.dataSource.next(message);
    }
}
