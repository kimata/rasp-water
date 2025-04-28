import { Component } from '@angular/core';
import { ToastComponent } from './toast/toast.component';
import { FooterComponent } from './footer/footer.component';
import { LogComponent } from './log/log.component';
import { ValveControlComponent } from './valve-control/valve-control.component';
import { SchedulerControlComponent } from './scheduler/scheduler-control/scheduler-control.component';
import { HeaderComponent } from './header/header.component';

@Component({
    selector: 'app-root',
    templateUrl: './app.component.html',
    styleUrls: ['./app.component.scss'],
    imports: [
        HeaderComponent,
        ValveControlComponent,
        SchedulerControlComponent,
        LogComponent,
        FooterComponent,
        ToastComponent,
    ]
})
export class AppComponent {}
