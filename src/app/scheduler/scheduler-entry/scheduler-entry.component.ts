import { Component, OnInit, EventEmitter, Input, Output, ChangeDetectorRef } from '@angular/core';
import { SchedulerControlComponent } from '../scheduler-control/scheduler-control.component';

import * as uuid from 'uuid';

@Component({
    selector: 'app-scheduler-entry',
    templateUrl: './scheduler-entry.component.html',
    styleUrls: ['./scheduler-entry.component.scss']
})

export class SchedulerEntryComponent implements OnInit {
    @Output() onChange = new EventEmitter();
    @Input() state;

    constructor(
        private control: SchedulerControlComponent,
        private changeDetectorRef: ChangeDetectorRef
    ) { }

    id = uuid.v4();

    timeOptions = {
        format: 'HH:mm',
    };

    ngOnInit() {
    }

    update() {
        if (this.state['wday'].filter(x => x).length == 0) {
            this.state['wday'] = new Array<boolean>(7).fill(true);
        }
        this.onChange.emit(this.state);
    }

    changeWday(event, i) {
        const wday = [...this.state['wday']];
        wday[i] = !wday[i];
        if (wday.filter(x => x).length == 0) {
            this.control.toast.show_info('いずれかの曜日を選択する必要があります。', {
                title: '通知',
            });

            event.preventDefault();
        }
    }
}
