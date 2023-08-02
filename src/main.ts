import { enableProdMode, importProvidersFrom } from '@angular/core';
import { platformBrowserDynamic } from '@angular/platform-browser-dynamic';

import { environment } from './environments/environment';
import { AppComponent } from './app/app.component';

import { NgbModule } from '@ng-bootstrap/ng-bootstrap';

import { BrowserModule, bootstrapApplication } from '@angular/platform-browser';
import { withInterceptorsFromDi, provideHttpClient, HttpClientJsonpModule } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

if (environment.production) {
    enableProdMode();
}

bootstrapApplication(AppComponent, {
    providers: [
        importProvidersFrom(FormsModule, HttpClientJsonpModule, BrowserModule, NgbModule),
        { provide: 'ApiEndpoint', useValue: '/rasp-water/api' },
        provideHttpClient(withInterceptorsFromDi()),
    ],
}).catch((err) => console.error(err));
