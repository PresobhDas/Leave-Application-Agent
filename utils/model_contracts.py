from pydantic import BaseModel
from typing import Literal, Optional

class WeatherData(BaseModel):
    latitude: float
    longitude: float
    temperature: float
    windspeed: float
    winddirection: float

class WeatherDataResponse(BaseModel):
    dataFound : Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    weatherData : WeatherData | None = None

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
    dataFound: Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    employee: EmployeeData | None = None

class EmployeeLeaveData(BaseModel):
    id:str
    employeeId:str
    name:str
    leaveType:str
    startDate:str
    endDate:str
    numberOfDays:int

class EmployeeLeaveResponseModel(BaseModel):
    dataFound : Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    employeeLeave : EmployeeLeaveData | None = None

class RagDataResponseModel(BaseModel):
    dataFound : Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    score:Optional[float] = 0.0
    text:Optional[str] = ''
    title:Optional[str] = ''

class InputDetails(BaseModel):
    inp_query:str