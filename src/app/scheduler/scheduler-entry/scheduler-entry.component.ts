import {
    Component,
    OnInit,
    EventEmitter,
    Input,
    Output,
    ChangeDetectorRef,
} from "@angular/core";
import { SchedulerControlComponent } from "../scheduler-control/scheduler-control.component";

import * as uuid from "uuid";
import { NgFor } from "@angular/common";
import { FormsModule } from "@angular/forms";

export interface ScheduleEntry {
    time: string;
    period: number;
    wday: boolean[];
    is_active: boolean;
}
@Component({
    selector: "app-scheduler-entry",
    templateUrl: "./scheduler-entry.component.html",
    styleUrls: ["./scheduler-entry.component.scss"],
    standalone: true,
    imports: [FormsModule, NgFor],
})
export class SchedulerEntryComponent implements OnInit {
    private _state = {
        time: "00:00",
        period: 0,
        wday: new Array<boolean>(7).fill(false),
        is_active: false,
    };

    @Output() stateChange = new EventEmitter();

    public get state(): ScheduleEntry {
        return this._state;
    }

    @Input()
    public set state(state: ScheduleEntry) {
        this._state = state;
        this.update();
    }

    constructor(
        private control: SchedulerControlComponent,
        private changeDetectorRef: ChangeDetectorRef
    ) {}

    readonly id = uuid.v4();

    timeOptions = {
        format: "HH:mm",
    };

    ngOnInit() {}

    update() {
        if (this._state["wday"].filter((x: boolean) => x).length == 0) {
            this._state["wday"] = new Array<boolean>(7).fill(true);
        }
        this.stateChange.emit(this.state);
        this.control.onChange();
    }

    changeWday(event: Event, i: number) {
        const wday = [...this.state["wday"]];
        wday[i] = !wday[i];
        if (wday.filter((x: Boolean) => x).length == 0) {
            this.control.toast.show_info(
                "いずれかの曜日を選択する必要があります。",
                {
                    title: "通知",
                }
            );

            event.preventDefault();
        }
    }
}
