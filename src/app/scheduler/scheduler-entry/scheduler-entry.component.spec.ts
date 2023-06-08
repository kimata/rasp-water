import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { SchedulerEntryComponent } from './scheduler-entry.component';

describe('SchedulerEntryComponent', () => {
  let component: SchedulerEntryComponent;
  let fixture: ComponentFixture<SchedulerEntryComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
    imports: [SchedulerEntryComponent]
})
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(SchedulerEntryComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
