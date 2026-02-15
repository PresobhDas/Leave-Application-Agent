from pydantic import BaseModel
from typing import Literal

class WeatherData(BaseModel):
    latitude: float
    longitude: float
    temperature: float
    windspeed: float
    winddirection: float

class EmployeeData(BaseModel):
    id:str
    employeeId:str
    name:str
    department:str
    managerId:str
    hireDate:str
    workLocation:str
    isActive:bool

class EmployeeMasterResponseModel(BaseModel):
    dataFound: Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'ERROR'
    employee: EmployeeData | None = None

class EmployeeLeaveData(BaseModel):
    id:str
    employeeId:str
    name:str
    leaveType:str
    startDate:str
    endDate:str
    numberOfDays:int

class RagData(BaseModel):
    id:str
    partiion_key_id:str
    test:str
    matchPercent:int

class InputDetails(BaseModel):
    inp_query:str