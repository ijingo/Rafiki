#!/usr/bin/python

import argparse
import os
import time
import glob
import sys

MESOS_ROOT="/opt/mesos-0.27.2/build"
PROTOBUF_PATH = MESOS_ROOT + "/3rdparty/libprocess/3rdparty/protobuf-2.5.0/python/"
for egg in glob.glob(os.path.join(MESOS_ROOT,'src','python','dist','*.egg')):
  sys.path.append(os.path.abspath(egg))

for egg in glob.glob(os.path.join(PROTOBUF_PATH,'dist','*.egg')):
  sys.path.append(os.path.abspath(egg))

import mesos.interface
from mesos.interface import mesos_pb2
import mesos.native

class SingaScheduler(mesos.interface.Scheduler):
  def __init__(self, implicitAcknowledgements, executor, args):
    self.implicitAcknowledgements = implicitAcknowledgements
    self.executor = executor
    self.required_cpu = args.CPU
    self.required_mem = args.MEM
    self.required_port = args.PORT
    self.url = args.url
    self.mode = args.mode
    self.frameworkID = ""
    self.taskID = ""
  
  def registered(self, driver, frameworkID, masterInfo):
    self.frameworkID = frameworkID.value
    self.taskID = self.frameworkID + "_task_0"
    print "Registered with framework ID %s" % frameworkID.value

  def resourceOffers(self, driver, offers):
    hasAccepted = False
    for offer in offers:
      print "Framework gets offer %s" % offer
      if not hasAccepted:
        if self.tryOffer(offer):
          print "Accept offer %s" % offer
      else:
        driver.declineOffer(offer.id)
        print "Declined offer %s" % offer

  def tryOffer(self, offer):
    offerCPUs = 0
    offerMEMs = 0
    offerPortBegin = 0
    offerPortEnd = 0

    for resource in offer.resources:
      if resource.name == "cpus":
        offerCPUs += resource.scalar.value
      elif resource.name == "mem":
        offerMEMs += resource.scalar.value
      elif resource.name == "ports":
        offerPortBegin = resource.ranges.range[0].begin
	offerPortEnd = resource.ranges.range[0].end

    if offerCPUs >= self.required_cpu and offerMEMs >= self.required_mem:
       #and offerPortBegin >= offerPortEnd and offerPortBegin > 0:
      print "Launching task using offer %s" % offer.id.value
      task = mesos_pb2.TaskInfo()
      container = mesos_pb2.ContainerInfo()
      container.type = mesos_pb2.ContainerInfo.DOCKER

      print "using port %s to %s" % (offerPortBegin, offerPortEnd)

      volume = container.volumes.add()
      volume.container_path = "/workspace"
      volume.host_path = "/var/opt/docker_singa_wokerspace/"+self.taskID
      volume.mode = mesos_pb2.Volume.RW

      command = mesos_pb2.CommandInfo()
      command.value = "/bin/bash /usr/src/incubator-singa/examples/cifar10_mesos/entry.sh "
                      + self.url + " "
                      + self.mode
#      command.value = "/usr/bin/python -m SimpleHTTPServer 80"
      task.command.MergeFrom(command)

      task.task_id.value = self.taskID
      task.slave_id.value = offer.slave_id.value
      task.name = "Singa task in docker"
      
      cpus = task.resources.add()
      cpus.name = "cpus"
      cpus.type = mesos_pb2.Value.SCALAR
      cpus.scalar.value = self.required_cpu

      mem = task.resources.add()
      mem.name = "mem"
      mem.type = mesos_pb2.Value.SCALAR
      mem.scalar.value = self.required_mem

      docker = mesos_pb2.ContainerInfo.DockerInfo()
      docker.image = "singa:latest"
      docker.network = mesos_pb2.ContainerInfo.DockerInfo.BRIDGE

      ports = task.resources.add()
      ports.name = "ports"
      ports.type = mesos_pb2.Value.RANGES
      ports_range = ports.ranges.range.add()
      #ports_range.begin = 31001
      #ports_range.end = 31001
      ports_range.begin = offerPortBegin
      ports_range.end = offerPortBegin
      docker_port = docker.port_mappings.add()
      docker_port.host_port = offerPortBegin
      docker_port.container_port = self.required_port

      container.docker.MergeFrom(docker)
      task.container.MergeFrom(container)

      tasks = []
      tasks.append(task)
      
      operation = mesos_pb2.Offer.Operation()
      operation.type = mesos_pb2.Offer.Operation.LAUNCH
      operation.launch.task_infos.extend(tasks)

      driver.acceptOffers([offer.id], [operation])
      
      return True
    else:
      return False

  def statusUpdate(self, driver, update):
    print "Task %s is in state %s" % \
      (update.task_id.value, mesos_pb2.TaskState.Name(update.state))

    if update.state == mesos_pb2.TASK_FINISHED:
      print "This task is finished"

    if update.state == mesos_pb2.TASK_LOST or \
       update.state == mesos_pb2.TASK_KILLED or \
       update.state == mesos_pb2.TASK_FAILED:
      print "Aborting because task %s is in unexpected state %s with message '%s'" \
        % (update.task_id.value, mesos_pb2.TaskState.Name(update.state), update.message)
      driver.abort()

    if not self.implicitAcknowledgements:
      driver.acknowlegeStatusUpdate(update)
      
if __name__ == "__main__":

  parser = argparse.ArgumentParser(description="Singa Framework for Mesos")
  parser.add_argument("-m", "--master", required=True, type=str,
      help="IP:Port of mesos master")
  parser.add_argument("--CPU", required=True, default=1, type=int,
      help="Number of CPUs requried to launch this job (default: 1)")
  parser.add_argument("--MEM", required=True, default=512, type=int,
      help="Total memory size requried to launch this job in MB (default: 512)")
  parser.add_argument("--PORT", required=True, type=int,
      help="Required Port in container")
  parser.add_argument("--url", required=True, type=str,
      help="URL for downloading the workspace folder content")
  parser.add_argument("--mode", required=True, type=str,
      help="Running mode(1 or 2): 1 for train or 2 for product")

  args = parser.parse_args()

  executor = mesos_pb2.ExecutorInfo()
  executor.executor_id.value = "singa_executor"
  executor.name = "Singa Executor in Docker"

  framework = mesos_pb2.FrameworkInfo()
  framework.user = ""
  framework.name = "Singa Framework"
  framework.checkpoint = False

  implicitAcknowledgements = 1
  if os.getenv("MESOS_EXPLICIT_ACKNOWLEDGEMENTS"):
    print "Enabling explicit status update acknowledgements"
    implicitAcknowledgements = 0

  framework.principal = "docker-mesos-singa-framework"
  driver = mesos.native.MesosSchedulerDriver(
      SingaScheduler(implicitAcknowledgements, executor, args),
      framework,
      args.master,
      implicitAcknowledgements)

  status = 0 if driver.run() == mesos_pb2.DRIVER_STOPPED else 1
  driver.stop()
  sys.exit(status)
