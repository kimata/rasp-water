import { Component } from '@angular/core';
import { ToastComponent } from './toast/toast.component';
import { FooterComponent } from './footer/footer.component';
import { LogComponent } from './log/log.component';
import { ValveControlComponent } from './valve-control/valve-control.component';
import { HeaderComponent } from './header/header.component';

@Component({
    selector: 'app-root',
    templateUrl: './app.component.html',
    styleUrls: ['./app.component.scss'],
    standalone: true,
    imports: [HeaderComponent, ValveControlComponent, LogComponent, FooterComponent, ToastComponent]
})

export class AppComponent {

}
