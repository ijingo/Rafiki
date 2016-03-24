#!usr/bin/env python

import argparse
import os
import time

import mesos.interface
from mesos.interface import mesos_pb2
import mesos.native

class SingaScheduler(mesos.interface.Scheduler):
  def __init__(self, implicitAcknowledgements, executor, args):
    self.implicitAcknowledgements = implicitAcknowledgements
    self.executor = executor
    self.required_cpu = args.CPU
    self.requried_mem = args.MEM
    self.url = args.url
    self.frameworkID = ""
    self.taskID = ""
  
  def registered(self, driver, frameworkID, masterInfo):
    self.frameworkID = frameworkID.value
    self.taskID = slef.frameworkID + "_task_0"
    print "Registered with framework ID %s" % frameworkID.value

  def resourceOffers(self, driver, offers):
    hasAccepted = False
    for offer in offers:
      print "Framework gets offer %s" % offer
      if not hasAccepted:
        if tryOffer(offer):
          print "Accept offer %s" % offer
      else:
        driver.declineOffer(offer.id)
        print "Declined offer %s" % offer

  def tryOffer(self, offer):
    offerCPUs = 0
    offerMEMs = 0
    for resource in offer.resources:
      if resource.name == "cpus":
        offerCPUs += resource.scalar.value
      elif resource.name == "mem":
        offerMEMs += resource.scalar.value

    if offerCPUs >= self.required_cpu and offerMEMs >= self.required_mem:
      print "Launching task using offer %s" % offer.id.value
      task = mesos_pb2.TaskInfo()
      container = mesos_pb2.ContainerInfo()
      ccontainer.type = mesos_pb2.ContainerInfo.Type.DOCKER

      volume = container.volumes.add()
      volume.container_path = "/workspace"
      volume.host_path = "/var/opt/docer_singa_wokerspace/"+self.taskID
      volume.mode = mesos_pb2.Volume.Mode.RW

      command = mesos_pb2.CommandInfo()
      command.value = "/usr/src/incubator-singa/examples/cifar10_mesos/entry.sh"
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
      docker.network = mesos_pb2.ContainerInfo.Network.BRIDGE

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
        % (update.task_id.value, mesos_pb2.TaskState.Name(update.state), update.messag)
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
  parser.add_argument("--url", required=True, type=str,
      help="URL for downloading the workspace folder content")

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
