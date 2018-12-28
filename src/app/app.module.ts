import { BrowserModule } from '@angular/platform-browser';
import { NgModule } from '@angular/core';
import { FormsModule } from '@angular/forms'
import { HttpClientModule, HttpClientJsonpModule } from '@angular/common/http';

import { NgbModule } from '@ng-bootstrap/ng-bootstrap';

import { AppComponent } from './app.component';

import { SchedulerModule } from './scheduler/scheduler.module';

import { ValveControlComponent } from './valve-control/valve-control.component';

import { HeaderComponent } from './header/header.component';
import { FooterComponent } from './footer/footer.component';
import { LogComponent } from './log/log.component';

@NgModule({
    declarations: [
        AppComponent,
        ValveControlComponent,
        HeaderComponent,
        FooterComponent,
        LogComponent,
    ],
    imports: [
        FormsModule,
        HttpClientModule,
        HttpClientJsonpModule,
        BrowserModule,
        NgbModule,
        SchedulerModule
    ],
    providers: [
        { provide: 'ApiEndpoint', useValue: 'http://192.168.2.247:5000/api' },
    ],
    bootstrap: [
        AppComponent
    ]
})

export class AppModule { }
