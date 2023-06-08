import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { SchedulerControlComponent } from './scheduler-control.component';

describe('SchedulerControlComponent', () => {
  let component: SchedulerControlComponent;
  let fixture: ComponentFixture<SchedulerControlComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
    imports: [SchedulerControlComponent]
})
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(SchedulerControlComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
